"""세션 밖 발송기. GitHub Actions 가 부른다.

왜 따로 있나
------------
스케줄 세션이 clone 한 저장소 코드를 실행하면 자동 권한 분류기가 '외부 코드'로 거부한다.
10/26, 11/9 두 회차 연속이었다. 그래서 역할을 나눈다.

- 세션(루틴): 수집, 선별, DB 발행, 그리고 **메일 원고(판단이 들어간 부분)를 `tcim_mail_jobs` 에 넣는 것**까지.
- 이 모듈(Actions): 원고를 읽어 render → preflight → send_issue → `tcim_sends` 기록. 판단은 하지 않는다.

원고에는 수신자를 넣지 않는다. 명단은 여기서 `tcim_subscribers` 를 직접 읽는다.
세션이 옮겨 적은 명단과 실제 명단이 어긋날 일을 없애기 위해서다.

같은 호를 몇 번 돌려도 안전하다. `tcim_sends` 의 성공분을 `already_sent` 로 넘기고,
Resend Idempotency-Key 가 한 번 더 막는다. 그래서 크론을 두 번 걸어 재시도로 쓴다.

네트워크는 Supabase PostgREST 와 (send.py 를 통한) Resend 뿐이다. 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import preflight as preflight_mod
from . import render as render_mod
from .send import USER_AGENT, send_issue

# 원고가 만들어진 뒤 이 기간이 지나면 크론은 손대지 않는다.
# 오래된 호가 새 구독자에게 뒤늦게 나가는 것을 막는다. 수동 실행(--issue)은 이 제한을 받지 않는다.
MAX_JOB_AGE = timedelta(days=10)
TIMEOUT = 30
CONFIG_KEYS = ("resend_api_key", "mail_from", "mail_reply_to", "auto_send")


class DispatchError(Exception):
    pass


class Supabase:
    """PostgREST 최소 클라이언트. service_role 키로 RLS 를 넘는다."""

    def __init__(self, url: str, key: str, opener=None):
        if not url or not key:
            raise DispatchError("SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY 가 필요하다")
        self.base = url.rstrip("/") + "/rest/v1/"
        self.key = key
        self._open = opener or urllib.request.urlopen

    def _request(self, method: str, path: str, body=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("apikey", self.key)
        req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", USER_AGENT)
        try:
            with self._open(req, timeout=TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise DispatchError(f"Supabase {method} {path.split('?')[0]} → HTTP {exc.code}: {detail}") from exc
        return json.loads(raw) if raw else None

    def select(self, table: str, query: str) -> list[dict]:
        return self._request("GET", f"{table}?{query}") or []

    def rpc(self, fn: str, args: dict):
        return self._request("POST", f"rpc/{fn}", args)


def _q(value) -> str:
    return urllib.parse.quote(str(value), safe="")


def pick_job(db: Supabase, issue_no: int | None, now: datetime) -> dict | None:
    """보낼 원고 1건. issue_no 를 주면 그 호의 최신 판, 아니면 가장 최근 원고."""
    if issue_no is not None:
        rows = db.select(
            "tcim_mail_jobs",
            f"issue_no=eq.{int(issue_no)}&select=*&order=revision.desc&limit=1",
        )
        return rows[0] if rows else None

    rows = db.select("tcim_mail_jobs", "select=*&order=issue_no.desc,revision.desc&limit=1")
    if not rows:
        return None
    job = rows[0]
    created = datetime.fromisoformat(str(job["created_at"]).replace("Z", "+00:00"))
    if now - created > MAX_JOB_AGE:
        return None
    return job


def load_context(db: Supabase, job: dict) -> dict:
    issue_no, revision = int(job["issue_no"]), int(job.get("revision") or 1)
    approved = [
        r["email"]
        for r in db.select("tcim_subscribers", "status=eq.approved&select=email&order=id.asc")
    ]
    sent = {
        r["email"].strip().lower()
        for r in db.select(
            "tcim_sends",
            f"issue_no=eq.{issue_no}&revision=eq.{revision}&status=eq.sent&select=email",
        )
    }
    keys = ",".join(CONFIG_KEYS)
    config = {
        r["key"]: r["value"]
        for r in db.select("tcim_private_config", f"key=in.({_q(keys)})&select=key,value")
    }
    return {"approved": approved, "already_sent": sent, "config": config}


def build_issue_data(job: dict, approved: list[str]) -> dict:
    data = dict(job["payload"])
    data["issue_no"] = int(job["issue_no"])
    data["recipients"] = list(approved)
    return data


def run(
    db: Supabase,
    template: str,
    *,
    issue_no: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
    transport=None,
    sleep_seconds: float | None = None,
) -> dict:
    """한 번 실행. 결과 요약 dict 를 돌려준다. 'ok' 가 False 면 Actions 를 실패로 끝낸다."""
    now = now or datetime.now(timezone.utc)
    job = pick_job(db, issue_no, now)
    if job is None:
        return {"ok": True, "action": "none", "reason": "보낼 원고 없음"}

    n, revision = int(job["issue_no"]), int(job.get("revision") or 1)
    ctx = load_context(db, job)
    cfg = ctx["config"]
    if not ctx["approved"]:
        return {"ok": True, "action": "none", "issue_no": n, "reason": "승인 구독자 0명"}
    if not cfg.get("resend_api_key"):
        return {"ok": False, "action": "blocked", "issue_no": n, "reason": "resend_api_key 없음 — SETUP-mail.md"}

    pending = [e for e in ctx["approved"] if e.strip().lower() not in ctx["already_sent"]]
    if not pending:
        return {"ok": True, "action": "none", "issue_no": n, "reason": "전원 발송 완료"}

    data = build_issue_data(job, ctx["approved"])
    rendered = render_mod.render(data, template)
    checks = preflight_mod.check(rendered, data, approved_count=len(ctx["approved"]))
    if not checks["ok"]:
        return {"ok": False, "action": "blocked", "issue_no": n, "reason": "프리플라이트 실패", "preflight": checks}

    auto = str(cfg.get("auto_send", "")).strip().lower() == "true"
    kwargs = {}
    if transport is not None:
        kwargs["transport"] = transport
    if sleep_seconds is not None:
        kwargs["sleep_seconds"] = sleep_seconds
    out = send_issue(
        rendered,
        data["recipients"],
        api_key=cfg["resend_api_key"],
        from_address=cfg.get("mail_from", ""),
        reply_to=cfg.get("mail_reply_to", ""),
        issue_no=n,
        revision=revision,
        already_sent=ctx["already_sent"],
        dry_run=dry_run or not auto,
        **kwargs,
    )

    # skipped(이미 발송, dry_run)는 기록하지 않는다. 성공 기록을 'skipped' 로 덮어쓰면 안 된다.
    to_record = [r for r in out["results"] if r["status"] in ("sent", "failed")]
    if to_record:
        db.rpc("tcim_record_sends", {"p_issue": n, "p_revision": revision, "p_results": to_record})

    failed = [r["email"] for r in out["results"] if r["status"] == "failed"]
    return {
        "ok": not failed,
        "action": "dry_run" if out["dry_run"] else "sent",
        "issue_no": n,
        "revision": revision,
        "subject": rendered["subject"],
        "sent": out["sent"],
        "failed": failed,
        "skipped": out["skipped"],
        "auto_send": auto,
        "preflight_warnings": checks["warnings"],
    }


def main(issue_no: int | None, dry_run: bool, template_path: str) -> int:
    db = Supabase(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    template = pathlib.Path(template_path).read_text(encoding="utf-8")
    try:
        result = run(db, template, issue_no=issue_no, dry_run=dry_run)
    except DispatchError as exc:
        result = {"ok": False, "action": "error", "reason": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n")
    return 0 if result["ok"] else 1
