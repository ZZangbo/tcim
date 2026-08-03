"""프리플라이트 테스트.

각 테스트는 "사람이 발송 버튼을 누르며 잡아냈어야 할 결함"을 하나씩 흉내낸다.
"""

import unittest

import fixture
from tcim.preflight import check
from tcim.render import render


def build(issue_no=3, approved=4, mutate_html=None, mutate_data=None):
    data = fixture.issue_data(issue_no)
    if mutate_data:
        mutate_data(data)
    rendered = render(data, fixture.template())
    if mutate_html:
        rendered["html"] = mutate_html(rendered["html"])
    return check(rendered, data, approved_count=approved)


def failed_on(result, needle):
    return any(needle in f for f in result["failures"])


class TestHappyPath(unittest.TestCase):
    def test_정상_렌더는_통과한다(self):
        r = build()
        self.assertTrue(r["ok"], r["failures"])
        self.assertEqual(r["failures"], [])

    def test_경고는_통과를_막지_않는다(self):
        r = check(render(fixture.issue_data(3), fixture.template()), fixture.issue_data(3))
        self.assertTrue(r["ok"], r["failures"])
        self.assertTrue(r["warnings"])


class TestGmailConstraints(unittest.TestCase):
    """Gmail 발송 파이프라인이 실제로 하는 일에 대응하는 검사들."""

    def test_배경색_선언을_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("padding:20px 10px;", "background:#0f6b5c;"))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "background"))

    def test_템플릿_주석의_background_는_오탐하지_않는다(self):
        """주석에 이 낱말이 설명으로 들어 있다. 떼어내지 않으면 항상 실패한다."""
        r = build()
        self.assertFalse(failed_on(r, "background"))

    def test_흰_글자를_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("color:#0f6b5c;font-size:20px", "color:#ffffff;font-size:20px"))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "흰 글자"))

    def test_짧은_흰색_표기도_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("color:#182029;", "color:#FFF;"))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "흰 글자"))

    def test_옅은_bgcolor_는_통과한다(self):
        r = build()
        self.assertFalse(failed_on(r, "bgcolor"))

    def test_어두운_bgcolor_를_잡는다(self):
        r = build(mutate_html=lambda h: h.replace('bgcolor="#f1f7f5"', 'bgcolor="#0f6b5c"'))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "bgcolor"))

    def test_맨_URL_앵커를_잡는다(self):
        r = build(
            mutate_html=lambda h: h.replace(
                ">zzangbo.github.io/tcim/?issue=3<", ">https://zzangbo.github.io/tcim/?issue=3<"
            )
        )
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "맨 URL"))

    def test_외부_이미지를_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("<body ", '<img src="https://x/y.png"><body '))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "외부 이미지"))


class TestIssueLink(unittest.TestCase):
    def test_어긋난_호_번호를_잡는다(self):
        """v2 템플릿의 실제 버그. 가시 링크만 제2호로 남아 있었다."""
        r = build(mutate_html=lambda h: h.replace(">zzangbo.github.io/tcim/?issue=3<", ">zzangbo.github.io/tcim/?issue=2<"))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "?issue="))

    def test_링크가_아예_없으면_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("?issue=3", "").replace("?issue=", ""))
        self.assertFalse(r["ok"])

    def test_링크가_모자라면_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("?issue=3", "?issue=x", 2))
        self.assertFalse(r["ok"])


class TestContent(unittest.TestCase):
    def test_헤드라인이_적으면_잡는다(self):
        r = build(mutate_data=lambda d: d.__setitem__("headlines", d["headlines"][:2]))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "헤드라인이 2건"))

    def test_헤드라인이_많으면_잡는다(self):
        r = build(mutate_data=lambda d: d.__setitem__("headlines", d["headlines"] * 2))
        self.assertFalse(r["ok"])

    def test_한_줄로_줄인_요약을_잡는다(self):
        def shorten(d):
            d["headlines"][1]["summary_ko"] = "중국이 5개년 계획을 냈습니다."

        r = build(mutate_data=shorten)
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "요약이"))

    def test_제목이_비면_잡는다(self):
        r = build(mutate_data=lambda d: d["headlines"][0].update({"title_ko": "", "title": ""}))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "제목이 없다"))

    def test_미치환_자리표시자를_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("2026년 8월 3일 – 8월 16일", "{{PERIOD}}"))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "자리표시자"))

    def test_수신_중단_안내가_빠지면_잡는다(self):
        r = build(mutate_html=lambda h: h.replace("수신을 중단하시려면", "안내 없음"))
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "수신 중단"))


class TestRecipients(unittest.TestCase):
    def test_수신자_수가_다르면_잡는다(self):
        r = build(approved=5)
        self.assertFalse(r["ok"])
        self.assertTrue(failed_on(r, "승인 구독자"))

    def test_수를_주지_않으면_경고만_남긴다(self):
        data = fixture.issue_data(3)
        r = check(render(data, fixture.template()), data, approved_count=None)
        self.assertTrue(r["ok"])
        self.assertTrue(any("건너뛰" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
