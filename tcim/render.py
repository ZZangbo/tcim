"""구독 메일 렌더링.

순수 함수다. 호 데이터와 템플릿 문자열을 받아 subject, html, text, headers 를 돌려준다.
DB 도 네트워크도 건드리지 않는다.

디자인 규칙은 RUNBOOK.md 5단계에 있고 그 근거는 DESIGN.md 에 있다.
요약하면 배경색에 의존하지 않고 흰 글자를 쓰지 않는다. Gmail 이 background 선언을 제거하기 때문이다.
"""

from __future__ import annotations

import html as _html
import re
from datetime import date

# 섹션별 라벨과 좌측 색띠. RUNBOOK.md 5단계의 값이다.
SECTIONS = {
    "policy": ("정책 규제", "#0f6b5c"),
    "evidence": ("근거 연구", "#3554a5"),
    "jobs": ("채용 공고", "#a05a1f"),
    "other": ("그 밖에", "#5d6b78"),
}
DEFAULT_SECTION = ("그 밖에", "#5d6b78")

ISSUE_URL = "https://zzangbo.github.io/tcim/?issue={issue_no}"

# 네이티브 구독취소 버튼을 띄운다. subject 를 TCIM 으로 지정한 이유는
# SUBSCRIBERS.md 4번의 회신 스캔 쿼리(subject:TCIM)에 그대로 걸리게 하기 위해서다.
#
# 이 주소는 Cloudflare Email Routing 이 jbh8284@gmail.com 으로 포워딩한다.
# 발신 도메인(news.jbhlab.com)에는 MX 가 없어서 거기로는 회신을 받을 수 없다.
# 푸터의 "이 메일에 회신해 주세요" 와 send.py 의 reply_to 가 모두 이 주소를 가리켜야
# 회신 기반 수신 중단 흐름이 성립한다.
UNSUBSCRIBE_MAILTO = "tcim@jbhlab.com"

CARD_START = "<!-- CARD:START -->"
CARD_END = "<!-- CARD:END -->"

FIRST_CARD_PAD = "14px 26px 0"
NEXT_CARD_PAD = "11px 26px 0"


def split_template(template: str) -> tuple[str, str]:
    """템플릿 파일을 (골격, 카드) 로 가른다.

    카드 블록이 있던 자리에 {{CARDS}} 를 남긴다. 덕분에 템플릿 파일은
    카드가 실제로 들어갈 위치에 카드 한 장을 그대로 두고 읽을 수 있다.
    """
    if CARD_START not in template or CARD_END not in template:
        raise ValueError("템플릿에 CARD:START / CARD:END 표시가 없다")
    head, rest = template.split(CARD_START, 1)
    card, tail = rest.split(CARD_END, 1)
    return head + "{{CARDS}}" + tail, card.strip()


def format_period(period_start: date, period_end: date) -> str:
    """'2026년 8월 3일 – 8월 16일'. 해가 바뀌면 뒤쪽에도 연도를 붙인다."""
    if period_start.year == period_end.year:
        return (
            f"{period_start.year}년 {period_start.month}월 {period_start.day}일"
            f" – {period_end.month}월 {period_end.day}일"
        )
    return (
        f"{period_start.year}년 {period_start.month}월 {period_start.day}일"
        f" – {period_end.year}년 {period_end.month}월 {period_end.day}일"
    )


def make_subject(issue_no: int, headlines: list[str], period_start: date, period_end: date) -> str:
    """'TCIM 브리핑 제3호 — 축약1, 축약2 (8/3~8/16)'

    축약 문구는 판단이라 LLM 이 만들어 넘긴다. 여기서는 조립만 한다.
    """
    head = ", ".join(h.strip() for h in headlines if h and h.strip())
    span = f"{period_start.month}/{period_start.day}~{period_end.month}/{period_end.day}"
    if head:
        return f"TCIM 브리핑 제{issue_no}호 — {head} ({span})"
    return f"TCIM 브리핑 제{issue_no}호 ({span})"


def _render_cards(card_tpl: str, items: list[dict]) -> str:
    out = []
    for idx, item in enumerate(items):
        label, color = SECTIONS.get(item.get("section", ""), DEFAULT_SECTION)
        block = card_tpl
        block = block.replace("{{CARD_PAD}}", FIRST_CARD_PAD if idx == 0 else NEXT_CARD_PAD)
        block = block.replace("{{SECTION_COLOR}}", color)
        block = block.replace("{{SECTION_LABEL}}", _html.escape(label))
        block = block.replace("{{REGION}}", _html.escape(item.get("region", "GLOBAL")))
        block = block.replace("{{TITLE}}", _html.escape(_title_of(item)))
        block = block.replace("{{SUMMARY}}", _html.escape(item.get("summary_ko", "").strip()))
        out.append(block)
    return "\n\n".join(out)


def _title_of(item: dict) -> str:
    return (item.get("title_ko") or item.get("title") or "").strip()


def render_text(data: dict, period_label: str) -> str:
    """평문 대체본. HTML 을 못 읽는 클라이언트가 받는다."""
    issue_no = data["issue_no"]
    lines = [
        "TCIM Global Watch",
        "전통의학과 보완통합의학 글로벌 동향 브리핑",
        f"제{issue_no}호 | {period_label}",
        "",
        data.get("intro", "").strip(),
        "",
    ]
    for item in data["headlines"]:
        label, _ = SECTIONS.get(item.get("section", ""), DEFAULT_SECTION)
        lines.append(f"[{label} | {item.get('region', 'GLOBAL')}] {_title_of(item)}")
        lines.append(item.get("summary_ko", "").strip())
        lines.append("")
    lines += [
        f"제{issue_no}호 전체 보기: {ISSUE_URL.format(issue_no=issue_no)}",
        "",
        data.get("counts", "").strip(),
        "",
        "경희대학교 한의과대학 예방의학교실 장보형 교수가 개인적으로 만들어 운영하는 브리핑입니다.",
        "요약은 자동 생성되므로 인용 전에는 원문을 확인해 주세요.",
        "수신을 중단하시려면 이 메일에 회신해 주세요.",
    ]
    return "\n".join(lines).strip() + "\n"


def render(data: dict, template: str) -> dict:
    """호 데이터와 템플릿 → {subject, html, text, headers}

    data 에 필요한 것:
        issue_no, period_start, period_end (date 또는 'YYYY-MM-DD'),
        intro, counts, subject_headlines[], headlines[]
    headlines 의 각 항목: title_ko 또는 title, summary_ko, section, region
    """
    issue_no = int(data["issue_no"])
    period_start = _as_date(data["period_start"])
    period_end = _as_date(data["period_end"])
    items = list(data["headlines"])

    skeleton, card_tpl = split_template(template)
    period_label = format_period(period_start, period_end)

    html_out = skeleton
    html_out = html_out.replace("{{CARDS}}", _render_cards(card_tpl, items))
    html_out = html_out.replace("{{PERIOD}}", _html.escape(period_label))
    html_out = html_out.replace("{{INTRO}}", _html.escape(data.get("intro", "").strip()))
    html_out = html_out.replace("{{COUNTS}}", _html.escape(data.get("counts", "").strip()))
    # ISSUE_NO 는 마지막에 치환한다. 카드 안에 들어갈 일은 없지만 순서 의존을 없애 둔다.
    html_out = html_out.replace("{{ISSUE_NO}}", str(issue_no))

    # 주석을 떼어낸 뒤 내보낸다. 템플릿 상단 주석은 배경색 제약과 자리표시자 목록을 적어 둔
    # 내부 문서인데, 그대로 두면 구독자에게 발송되는 본문에 실려 나간다. 카드 분리에 쓰는
    # CARD:START 표시도 여기서 함께 사라진다.
    html_out = _tidy(strip_html_comments(html_out))

    return {
        "subject": make_subject(
            issue_no, data.get("subject_headlines", []), period_start, period_end
        ),
        "html": html_out,
        "text": render_text(
            {**data, "issue_no": issue_no, "headlines": items}, period_label
        ),
        "headers": {
            "List-Unsubscribe": f"<mailto:{UNSUBSCRIBE_MAILTO}?subject=TCIM unsubscribe>",
            "List-Id": "TCIM Global Watch <tcim.jbhlab.com>",
        },
    }


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _tidy(markup: str) -> str:
    """주석을 떼어낸 자리에 남는 빈 줄을 정리한다."""
    return re.sub(r"\n{3,}", "\n\n", markup).strip() + "\n"


def strip_html_comments(markup: str) -> str:
    """검사 전에 주석을 떼어낸다.

    템플릿 주석에 'background' 라는 낱말이 들어 있어서, 떼어내지 않으면
    프리플라이트의 배경색 검사가 자기 자신의 설명문에 걸려 항상 실패한다.
    """
    return re.sub(r"<!--.*?-->", "", markup, flags=re.DOTALL)
