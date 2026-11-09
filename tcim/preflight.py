"""발송 직전 자동 검사.

사람이 발송 버튼을 누르며 실제로 잡아내던 것은 기계적 결함이었다. 그 자리를 대신한다.
하나라도 실패하면 발송하지 않는다.

순수 함수다. 렌더 결과와 데이터만 보고 판정한다.
검사를 넣은 이유는 각 함수의 docstring 에 있다. 이유 없는 검사는 넣지 않는다.
"""

from __future__ import annotations

import re

from .render import strip_html_comments

MIN_HEADLINES = 3
MAX_HEADLINES = 5
MIN_SUMMARY_CHARS = 60  # 2~3문장이면 넉넉히 넘는다. "한 줄로 줄이지 말 것"의 기계적 하한
MAX_RESEARCH = 5
MIN_RESEARCH_SUMMARY_CHARS = 40  # 1~2문장. 제목만 다시 적는 것을 막는 하한
MIN_BGCOLOR_LUMINANCE = 0.75  # 이보다 어두우면 글자가 안 읽힐 위험이 있다

_ANCHOR = re.compile(r"<a\b[^>]*>(.*?)</a>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BACKGROUND = re.compile(r"background(?:-color)?\s*:", re.IGNORECASE)
_WHITE_TEXT = re.compile(r"color\s*:\s*(?:#fff\b|#ffffff\b|white\b)", re.IGNORECASE)
_ISSUE_LINK = re.compile(r"\?issue=(\d+)")
_PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")
_BGCOLOR = re.compile(r'bgcolor\s*=\s*"(#[0-9a-fA-F]{6})"')
_RESEARCH_LINK = re.compile(r">\s*DOI 보기\s*</a>")
_EXTERNAL_ASSET = re.compile(r"(<img\b|@import|url\(\s*['\"]?https?:)", re.IGNORECASE)

UNSUBSCRIBE_NOTICE = "수신을 중단하시려면"


def check(rendered: dict, data: dict, approved_count: int | None = None) -> dict:
    """전체 검사.

    Args:
        rendered: render() 의 반환값
        data: render() 에 넣은 호 데이터
        approved_count: 승인된 구독자 수. 주면 수신자 수와 대조한다.

    Returns:
        {"ok": bool, "failures": [...], "warnings": [...], "checked": int}
    """
    html = rendered.get("html", "")
    body = strip_html_comments(html)
    failures: list[str] = []
    warnings: list[str] = []

    _check_headlines(data, failures)
    _check_background(body, failures)
    _check_white_text(body, failures)
    _check_bgcolor_luminance(body, failures)
    _check_bare_url_anchors(body, failures)
    _check_issue_links(body, data, failures)
    _check_placeholders(body, failures)
    _check_unsubscribe_notice(body, failures)
    _check_external_assets(body, failures)
    _check_subject(rendered, data, failures)
    _check_text_alternative(rendered, failures)
    _check_headers(rendered, failures)
    _check_recipients(data, approved_count, failures, warnings)
    _check_research(body, rendered, data, failures, warnings)

    return {
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "checked": 14,
    }


def _check_headlines(data: dict, failures: list[str]) -> None:
    """헤드라인 3~5건, 모든 항목에 제목과 충분한 길이의 요약. RUNBOOK.md 3단계 선정 규칙."""
    items = data.get("headlines") or []
    if not MIN_HEADLINES <= len(items) <= MAX_HEADLINES:
        failures.append(
            f"헤드라인이 {len(items)}건이다. {MIN_HEADLINES}~{MAX_HEADLINES}건이어야 한다"
        )
    for idx, item in enumerate(items, 1):
        title = (item.get("title_ko") or item.get("title") or "").strip()
        summary = (item.get("summary_ko") or "").strip()
        if not title:
            failures.append(f"{idx}번 항목에 제목이 없다")
        if len(summary) < MIN_SUMMARY_CHARS:
            failures.append(
                f"{idx}번 항목의 요약이 {len(summary)}자다. "
                f"{MIN_SUMMARY_CHARS}자 이상이어야 한다 (제목: {title[:24]})"
            )


def _check_background(body: str, failures: list[str]) -> None:
    """Gmail 이 background 와 background-color 선언을 전부 제거한다.

    2026-08-03 실제 발송본에서 확인했다. 살아남는 것은 border, color, padding, border-radius 다.
    주석을 먼저 떼어내는 이유는 템플릿 주석에 이 낱말이 설명으로 들어 있기 때문이다.
    """
    if _BACKGROUND.search(body):
        failures.append("HTML 에 background CSS 선언이 있다. Gmail 이 제거하므로 의존하면 안 된다")


def _check_white_text(body: str, failures: list[str]) -> None:
    """배경이 사라지는 순간 흰 바탕에 흰 글자가 되어 안 보인다."""
    found = _WHITE_TEXT.findall(body)
    if found:
        failures.append(f"흰 글자가 있다 ({len(found)}곳). 배경이 제거되면 읽히지 않는다")


def _check_bgcolor_luminance(body: str, failures: list[str]) -> None:
    """bgcolor 속성은 옅은 톤에만. 제거되든 남든 어두운 글자가 읽혀야 한다."""
    for value in _BGCOLOR.findall(body):
        if _luminance(value) < MIN_BGCOLOR_LUMINANCE:
            failures.append(f"bgcolor {value} 가 너무 어둡다. 옅은 톤만 쓴다")


def _check_bare_url_anchors(body: str, failures: list[str]) -> None:
    """맨 URL 을 앵커 텍스트로 두면 Gmail 이 google.com/url?q= 로 감싸 흉하게 보인다.

    scheme 없는 zzangbo.github.io/... 표기는 의도된 이중 안전장치라 허용한다.
    """
    for raw in _ANCHOR.findall(body):
        text = _TAG.sub("", raw).strip()
        if text.lower().startswith(("http://", "https://")):
            failures.append(f"앵커 텍스트가 맨 URL 이다: {text[:60]}")


def _check_issue_links(body: str, data: dict, failures: list[str]) -> None:
    """?issue=N 이 href 와 가시 텍스트 모두에서 이번 호를 가리켜야 한다.

    v2 템플릿의 가시 링크에 ?issue=2 가 하드코딩돼 있어 제3호부터 제2호로 연결됐을 검사다.
    """
    issue_no = str(data.get("issue_no"))
    found = _ISSUE_LINK.findall(body)
    if not found:
        failures.append("?issue=N 링크가 없다")
        return
    wrong = sorted({n for n in found if n != issue_no})
    if wrong:
        failures.append(f"?issue= 값이 이번 호({issue_no})와 다르다: {', '.join(wrong)}")
    if len(found) < 3:
        failures.append(
            f"?issue= 링크가 {len(found)}곳뿐이다. 버튼 href, 대체 href, 가시 텍스트 셋이어야 한다"
        )


def _check_placeholders(body: str, failures: list[str]) -> None:
    """미치환 자리표시자가 그대로 나가면 바로 보인다."""
    left = sorted(set(_PLACEHOLDER.findall(body)))
    if left:
        failures.append(f"치환되지 않은 자리표시자가 있다: {', '.join(left)}")


def _check_unsubscribe_notice(body: str, failures: list[str]) -> None:
    """수신 중단 안내는 회신 기반 흐름의 입구다. 빠지면 나갈 길이 없어진다."""
    if UNSUBSCRIBE_NOTICE not in body:
        failures.append("수신 중단 안내 문구가 없다")


def _check_external_assets(body: str, failures: list[str]) -> None:
    """외부 이미지와 웹폰트는 네이버와 다음 웹메일에서 깨지거나 차단된다."""
    if _EXTERNAL_ASSET.search(body):
        failures.append("외부 이미지나 웹폰트 참조가 있다")


def _check_subject(rendered: dict, data: dict, failures: list[str]) -> None:
    subject = rendered.get("subject", "")
    if not subject.strip():
        failures.append("제목이 비어 있다")
        return
    if f"제{data.get('issue_no')}호" not in subject:
        failures.append(f"제목에 '제{data.get('issue_no')}호'가 없다: {subject}")


def _check_text_alternative(rendered: dict, failures: list[str]) -> None:
    """평문 대체본이 없으면 일부 클라이언트에서 빈 메일로 보인다."""
    text = rendered.get("text", "")
    if len(text.strip()) < 200:
        failures.append(f"평문 대체본이 {len(text.strip())}자로 너무 짧다")


def _check_headers(rendered: dict, failures: list[str]) -> None:
    """List-Unsubscribe 는 도달률에 가장 크게 기여하고 비용이 0이다.

    subject 를 TCIM 으로 지정해 두어야 SUBSCRIBERS.md 4번의 회신 스캔에 걸린다.
    """
    header = rendered.get("headers", {}).get("List-Unsubscribe", "")
    if not header:
        failures.append("List-Unsubscribe 헤더가 없다")
    elif "subject=TCIM" not in header:
        failures.append("List-Unsubscribe 의 subject 가 TCIM 이 아니라 회신 스캔에 안 걸린다")


def _check_recipients(
    data: dict, approved_count: int | None, failures: list[str], warnings: list[str]
) -> None:
    """명단 쿼리와 실제 발송 대상이 어긋나는 것을 막는다."""
    if approved_count is None:
        warnings.append("승인 구독자 수를 주지 않아 수신자 대조를 건너뛰었다")
        return
    recipients = data.get("recipients")
    if recipients is None:
        warnings.append("수신자 목록이 없어 대조를 건너뛰었다")
        return
    if len(recipients) != approved_count:
        failures.append(
            f"수신자 {len(recipients)}명과 승인 구독자 {approved_count}명이 다르다"
        )


def _check_research(
    body: str, rendered: dict, data: dict, failures: list[str], warnings: list[str]
) -> None:
    """'이번 호 주요 연구' 절. 선택 항목이라 비어 있으면 경고만 한다.

    PubMed 가 붙지 않은 회차에는 문헌이 없을 수 있다. 그때 발송까지 막으면 정책 소식도 못 나간다.
    있으면 항목마다 제목, 출처, 요약, DOI 링크가 갖춰져야 하고 렌더 결과에 빠짐없이 실려야 한다.
    """
    items = data.get("research") or []
    if not items:
        warnings.append("주요 연구 절이 비어 있어 메일에서 빠졌다")
        return
    if len(items) > MAX_RESEARCH:
        failures.append(f"주요 연구가 {len(items)}편이다. {MAX_RESEARCH}편 이하여야 한다")
    for idx, item in enumerate(items, 1):
        title = (item.get("title_ko") or item.get("title") or "").strip()
        summary = str(item.get("summary_ko") or "").strip()
        url = str(item.get("url") or "").strip()
        label = f"주요 연구 {idx}번"
        if not title:
            failures.append(f"{label}에 제목이 없다")
        if not str(item.get("journal") or "").strip():
            failures.append(f"{label}에 저널명이 없다 (제목: {title[:24]})")
        if len(summary) < MIN_RESEARCH_SUMMARY_CHARS:
            failures.append(
                f"{label}의 요약이 {len(summary)}자다. {MIN_RESEARCH_SUMMARY_CHARS}자 이상이어야 한다"
            )
        if not url.startswith("https://"):
            failures.append(f"{label}의 링크가 https 주소가 아니다: {url[:60]}")
        elif not url.startswith("https://doi.org/"):
            warnings.append(f"{label}의 링크가 DOI 주소가 아니다: {url[:60]}")
    shown = len(_RESEARCH_LINK.findall(body))
    if shown != len(items):
        failures.append(f"주요 연구 {len(items)}편 중 메일에 실린 링크가 {shown}개다")
    if "이번 호 주요 연구" not in rendered.get("text", ""):
        failures.append("평문 대체본에 주요 연구 절이 없다")


def _luminance(hex_color: str) -> float:
    """WCAG 상대 휘도."""
    value = hex_color.lstrip("#")
    parts = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
