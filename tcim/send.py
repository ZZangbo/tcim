"""발송. 이 패키지에서 네트워크와 자격증명을 만지는 유일한 모듈이다.

**수신자 한 명당 한 통씩 보낸다.** BCC 로 묶지 않는다.
BCC 묶음은 개인 Gmail 시절의 우회책이었다. ESP 를 쓰면 한 통씩 보내는 편이 낫다.

- 수신자별로 성공과 실패를 정확히 안다. `tcim_sends` 가 추측이 아니라 사실이 된다
- 받는 사람 To 에 자기 주소가 보인다. 단체 발송 티가 덜 난다
- 한 명이 실패해도 나머지가 나간다

DB 는 건드리지 않는다. 결과를 돌려주면 세션이 `tcim_sends` 에 기록한다.
자격증명을 쥔 모듈이 DB 까지 쥐지 않게 하려는 것이다.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request

RESEND_ENDPOINT = "https://api.resend.com/emails"

# ★반드시 보내야 한다. api.resend.com 은 Cloudflare 뒤에 있고, urllib 의 기본
# User-Agent(`Python-urllib/3.x`)로 요청하면 봇으로 분류돼 **403 error 1010** 이 온다.
# 2026-08-03 실측이다. 값 자체는 아무거나 되지만 비어 있으면 안 된다.
USER_AGENT = "tcim-global-watch/1.0"

# Resend 는 초당 요청 수에 제한이 있다. 정확한 값에 기대지 않고 넉넉히 벌린다.
# 4명이면 체감이 없고 100명이어도 1분이다.
DEFAULT_SLEEP = 0.6
MAX_RETRIES = 2
RETRY_STATUSES = {429, 500, 502, 503, 504}
TIMEOUT = 30


class SendError(Exception):
    pass


def _http_post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("User-Agent", USER_AGENT)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = {"message": raw[:300]}
        return exc.code, parsed
    except Exception as exc:  # 네트워크 계층 실패
        raise SendError(f"{type(exc).__name__}: {exc}") from exc


def _idempotency_key(issue_no: int, email: str) -> str:
    """같은 호를 같은 사람에게 두 번 보내지 않게 한다.

    재시도가 중복 발송이 되는 것을 provider 쪽에서도 막는다.
    DB 의 (issue_no, lower(email)) 유니크 인덱스와 이중 방어다.
    """
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"tcim-{issue_no}-{digest}"


def _resend_payload(rendered: dict, recipient: str, from_address: str, reply_to: str) -> dict:
    payload = {
        "from": from_address,
        "to": [recipient],
        "subject": rendered["subject"],
        "html": rendered["html"],
        "text": rendered["text"],
        "headers": dict(rendered.get("headers", {})),
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
    return payload


def send_one(
    rendered: dict,
    recipient: str,
    *,
    api_key: str,
    from_address: str,
    reply_to: str,
    issue_no: int,
    transport=None,
    sleep_seconds: float = DEFAULT_SLEEP,
) -> dict:
    """한 명에게 보낸다. 결과 dict 를 돌려주고 예외를 던지지 않는다."""
    transport = transport or _http_post
    payload = _resend_payload(rendered, recipient, from_address, reply_to)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": _idempotency_key(issue_no, recipient),
    }

    last_error = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            status, body = transport(RESEND_ENDPOINT, payload, headers)
        except SendError as exc:
            last_error = str(exc)
            status, body = 0, {}

        if 200 <= status < 300:
            return {
                "email": recipient,
                "status": "sent",
                "provider": "resend",
                "provider_id": body.get("id"),
                "error": None,
                "attempts": attempt + 1,
            }

        if status and status not in RETRY_STATUSES:
            # 400 대는 다시 보내도 같은 결과다. 주소 오류나 도메인 미검증이 여기 온다.
            return {
                "email": recipient,
                "status": "failed",
                "provider": "resend",
                "provider_id": None,
                "error": f"HTTP {status}: {_message(body)}"[:400],
                "attempts": attempt + 1,
            }

        last_error = f"HTTP {status}: {_message(body)}" if status else last_error
        if attempt < MAX_RETRIES:
            time.sleep(sleep_seconds * (2**attempt))

    return {
        "email": recipient,
        "status": "failed",
        "provider": "resend",
        "provider_id": None,
        "error": (last_error or "알 수 없는 실패")[:400],
        "attempts": MAX_RETRIES + 1,
    }


def send_issue(
    rendered: dict,
    recipients: list[str],
    *,
    api_key: str,
    from_address: str,
    reply_to: str,
    issue_no: int,
    already_sent: set[str] | None = None,
    dry_run: bool = False,
    transport=None,
    sleep_seconds: float = DEFAULT_SLEEP,
) -> dict:
    """수신자 전원에게 한 통씩.

    Args:
        already_sent: 이미 보낸 주소. `tcim_sends` 에서 읽어 넘기면 재시도 때
            성공분을 건너뛴다. 소문자로 비교한다.
        dry_run: 실제로 보내지 않고 대상만 확인한다. `auto_send=false` 인 회차용.

    Returns:
        {"results": [...], "sent": n, "failed": n, "skipped": n, "dry_run": bool}
    """
    done = {e.strip().lower() for e in (already_sent or set())}
    results = []

    for idx, raw in enumerate(recipients):
        recipient = raw.strip()
        if not recipient:
            continue
        if recipient.lower() in done:
            results.append(
                {
                    "email": recipient,
                    "status": "skipped",
                    "provider": "resend",
                    "provider_id": None,
                    "error": "이미 발송됨",
                    "attempts": 0,
                }
            )
            continue
        if dry_run:
            results.append(
                {
                    "email": recipient,
                    "status": "skipped",
                    "provider": "resend",
                    "provider_id": None,
                    "error": "dry_run",
                    "attempts": 0,
                }
            )
            continue

        if idx:
            time.sleep(sleep_seconds)
        results.append(
            send_one(
                rendered,
                recipient,
                api_key=api_key,
                from_address=from_address,
                reply_to=reply_to,
                issue_no=issue_no,
                transport=transport,
                sleep_seconds=sleep_seconds,
            )
        )

    return {
        "results": results,
        "sent": sum(1 for r in results if r["status"] == "sent"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "dry_run": dry_run,
    }


def _message(body: dict) -> str:
    if not isinstance(body, dict):
        return str(body)[:200]
    return str(body.get("message") or body.get("error") or body)[:200]
