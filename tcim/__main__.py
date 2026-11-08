"""CLI. 결과는 stdout 에 JSON 으로 나간다 — 세션이 그대로 파싱한다.

  python3 -m tcim plan --today 2026-08-17 --last-end 2026-08-02 --last-issue 2
  python3 -m tcim build --data issue.json --template email-template.html --approved 4 --out ./out
  python3 -m tcim dispatch [--issue N] [--dry-run]   # GitHub Actions 전용. SUPABASE_* 환경변수 필요
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date

from . import preflight as preflight_mod
from . import render as render_mod
from .plan import make_plan


def _cmd_plan(args: argparse.Namespace) -> int:
    result = make_plan(
        today=date.fromisoformat(args.today),
        last_period_end=date.fromisoformat(args.last_end) if args.last_end else None,
        last_issue_no=args.last_issue,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    data = json.loads(pathlib.Path(args.data).read_text(encoding="utf-8"))
    template = pathlib.Path(args.template).read_text(encoding="utf-8")

    rendered = render_mod.render(data, template)
    checks = preflight_mod.check(rendered, data, approved_count=args.approved)

    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "mail.html").write_text(rendered["html"], encoding="utf-8")
        (out / "mail.txt").write_text(rendered["text"], encoding="utf-8")

    json.dump(
        {
            "subject": rendered["subject"],
            "headers": rendered["headers"],
            "html_bytes": len(rendered["html"].encode("utf-8")),
            "text_bytes": len(rendered["text"].encode("utf-8")),
            "preflight": checks,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    # 프리플라이트가 실패하면 종료 코드를 1로 둔다. 발송 단계가 이걸 보고 멈춘다.
    return 0 if checks["ok"] else 1


def _cmd_dispatch(args: argparse.Namespace) -> int:
    from .dispatch import main as dispatch_main  # 네트워크 모듈은 쓸 때만 불러온다

    return dispatch_main(args.issue, args.dry_run, args.template)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tcim")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="발행 여부와 수집 기간 계산")
    p.add_argument("--today", required=True, help="실행일 KST, YYYY-MM-DD")
    p.add_argument("--last-end", help="직전 호 period_end. 첫 발행이면 생략")
    p.add_argument("--last-issue", type=int, help="직전 호 issue_no. 첫 발행이면 생략")
    p.set_defaults(func=_cmd_plan)

    b = sub.add_parser("build", help="메일 렌더링과 프리플라이트")
    b.add_argument("--data", required=True, help="호 데이터 JSON 경로")
    b.add_argument("--template", required=True, help="email-template.html 경로")
    b.add_argument("--approved", type=int, help="승인 구독자 수. 주면 수신자와 대조한다")
    b.add_argument("--out", help="mail.html 과 mail.txt 를 쓸 디렉터리")
    b.set_defaults(func=_cmd_build)

    d = sub.add_parser("dispatch", help="tcim_mail_jobs 원고를 읽어 발송 (GitHub Actions 용)")
    d.add_argument("--issue", type=int, help="이 호를 보낸다. 생략하면 10일 이내 가장 최근 원고")
    d.add_argument("--dry-run", action="store_true", help="렌더와 프리플라이트만, 발송하지 않음")
    d.add_argument("--template", default="email-template.html", help="email-template.html 경로")
    d.set_defaults(func=_cmd_dispatch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
