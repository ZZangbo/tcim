"""발행 계획 계산.

순수 함수다. 네트워크도 자격증명도 파일도 건드리지 않는다.
직전 발행 상태와 오늘 날짜만 받아서 "이번 회차에 발행할지, 한다면 어느 기간을"을 돌려준다.

RUNBOOK.md 1단계의 규칙을 그대로 옮긴 것이다. 규칙을 바꾸려면 런북과 이 파일을 함께 고친다.
"""

from __future__ import annotations

from datetime import date, timedelta

# 직전 period_end 로부터 이 일수가 지나야 발행한다.
# 14가 아니라 13인 이유: 실행 시각이 몇 분 밀리거나 앞당겨져도 격주 리듬이
# 한 주씩 밀리지 않게 하려는 것이다. 14로 잡으면 몇 분 차이로 한 주를 통째로 거른다.
GUARD_DAYS = 13

# briefings 가 비어 있을 때 최초 회차가 훑는 기간
FIRST_PERIOD_DAYS = 14

# 수집 기간이 이보다 길면 결번을 메우는 백필이다.
# 정상 격주 주기에서는 정확히 14일이 나온다(주간 크론 + period_end = 실행일 전날).
BACKFILL_THRESHOLD_DAYS = 15

MONDAY = 0


def _iso_week(d: date) -> str:
    """'YYYY-Www' 형식. tcim_items.week_no 규약이다."""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _next_publish_monday(today: date, last_period_end: date) -> date:
    """가드를 통과하는 다음 월요일. 크론이 월요일에만 깨어나므로 월요일만 후보다."""
    d = today + timedelta(days=1)
    for _ in range(400):  # 폭주 방지. 정상적으로는 14일 안에 걸린다
        if d.weekday() == MONDAY and (d - last_period_end).days >= GUARD_DAYS:
            return d
        d += timedelta(days=1)
    raise RuntimeError("다음 발행일을 찾지 못했다")


def make_plan(
    today: date,
    last_period_end: date | None = None,
    last_issue_no: int | None = None,
) -> dict:
    """이번 회차의 발행 계획.

    Args:
        today: 실행일(KST 기준). 수집 기간의 끝은 이 날의 전날이다.
        last_period_end: 직전 호의 period_end. 첫 발행이면 None.
        last_issue_no: 직전 호의 issue_no. 첫 발행이면 None.

    Returns:
        should_publish, notify, reason, issue_no, period_start, period_end,
        period_days, week_no, days_since_last, backfill, next_publish 를 담은 dict.
        날짜는 전부 'YYYY-MM-DD' 문자열이다.
    """
    period_end = today - timedelta(days=1)

    # 첫 발행
    if last_period_end is None:
        period_start = period_end - timedelta(days=FIRST_PERIOD_DAYS - 1)
        return _result(
            should_publish=True,
            notify=True,
            reason="최초 발행",
            issue_no=0 if last_issue_no is None else last_issue_no + 1,
            period_start=period_start,
            period_end=period_end,
            days_since_last=None,
            next_publish=None,
        )

    days_since_last = (today - last_period_end).days
    period_start = last_period_end + timedelta(days=1)

    # 격주 가드. 쉬는 주는 알림도 보내지 않는다 — 매주 "이번 주는 쉽니다"가 오면 소음이다.
    if days_since_last < GUARD_DAYS:
        return _result(
            should_publish=False,
            notify=False,
            reason="격주 주기 — 이번 주는 건너뜀",
            issue_no=None,
            period_start=period_start,
            period_end=period_end,
            days_since_last=days_since_last,
            next_publish=_next_publish_monday(today, last_period_end),
        )

    # 이미 커버된 기간. 가드보다 뒤에 둔 이유는 가드에 걸린 회차가 대부분이기 때문이다.
    if period_start > period_end:
        return _result(
            should_publish=False,
            notify=True,
            reason="신규 기간 없음",
            issue_no=None,
            period_start=period_start,
            period_end=period_end,
            days_since_last=days_since_last,
            next_publish=_next_publish_monday(today, last_period_end),
        )

    return _result(
        should_publish=True,
        notify=True,
        reason="정상 주기",
        issue_no=(0 if last_issue_no is None else last_issue_no + 1),
        period_start=period_start,
        period_end=period_end,
        days_since_last=days_since_last,
        next_publish=None,
    )


def _result(
    *,
    should_publish: bool,
    notify: bool,
    reason: str,
    issue_no: int | None,
    period_start: date,
    period_end: date,
    days_since_last: int | None,
    next_publish: date | None,
) -> dict:
    period_days = (period_end - period_start).days + 1
    return {
        "should_publish": should_publish,
        "notify": notify,
        "reason": reason,
        "issue_no": issue_no,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_days": period_days,
        "week_no": _iso_week(period_end),
        "days_since_last": days_since_last,
        "backfill": period_days > BACKFILL_THRESHOLD_DAYS,
        "next_publish": next_publish.isoformat() if next_publish else None,
    }
