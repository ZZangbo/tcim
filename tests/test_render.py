import re
import unittest
from datetime import date

import fixture
from tcim.render import format_period, make_subject, render, split_template


class TestTemplate(unittest.TestCase):
    def test_카드_블록을_가르고_자리를_남긴다(self):
        skeleton, card = split_template(fixture.template())
        self.assertIn("{{CARDS}}", skeleton)
        self.assertNotIn("<!-- CARD:START -->", skeleton)
        self.assertIn("{{TITLE}}", card)
        self.assertIn("{{SUMMARY}}", card)

    def test_표시가_없으면_거부한다(self):
        with self.assertRaises(ValueError):
            split_template("<html></html>")


class TestSubject(unittest.TestCase):
    def test_형식(self):
        s = make_subject(3, ["BRICS 전통의학 선언", "중국 5개년 계획"], date(2026, 8, 3), date(2026, 8, 16))
        self.assertEqual(s, "TCIM 브리핑 제3호 — BRICS 전통의학 선언, 중국 5개년 계획 (8/3~8/16)")

    def test_축약_문구가_없어도_깨지지_않는다(self):
        s = make_subject(3, [], date(2026, 8, 3), date(2026, 8, 16))
        self.assertEqual(s, "TCIM 브리핑 제3호 (8/3~8/16)")

    def test_빈_문자열은_걸러진다(self):
        s = make_subject(3, ["", "  ", "실제 문구"], date(2026, 8, 3), date(2026, 8, 16))
        self.assertIn("— 실제 문구 (", s)


class TestPeriodLabel(unittest.TestCase):
    def test_같은_해면_연도를_한_번만(self):
        self.assertEqual(
            format_period(date(2026, 8, 3), date(2026, 8, 16)), "2026년 8월 3일 – 8월 16일"
        )

    def test_해를_넘기면_양쪽에_연도를(self):
        self.assertEqual(
            format_period(date(2026, 12, 28), date(2027, 1, 10)),
            "2026년 12월 28일 – 2027년 1월 10일",
        )


class TestRender(unittest.TestCase):
    def setUp(self):
        self.data = fixture.issue_data(3)
        self.out = render(self.data, fixture.template())

    def test_카드가_헤드라인_수만큼_복제된다(self):
        self.assertEqual(self.out["html"].count("border-left:4px solid"), 4)

    def test_모든_제목이_들어간다(self):
        for item in self.data["headlines"]:
            self.assertIn(item["title_ko"], self.out["html"])

    def test_섹션별_색이_다르다(self):
        self.assertIn("#0f6b5c", self.out["html"])  # policy
        self.assertIn("#3554a5", self.out["html"])  # evidence

    def test_섹션_라벨이_한국어다(self):
        self.assertIn("정책 규제", self.out["html"])
        self.assertIn("근거 연구", self.out["html"])

    def test_자리표시자가_남지_않는다(self):
        self.assertEqual(re.findall(r"\{\{[A-Z_]+\}\}", self.out["html"]), [])

    def test_issue_링크가_전부_이번_호를_가리킨다(self):
        found = re.findall(r"\?issue=(\d+)", self.out["html"])
        self.assertTrue(found)
        self.assertEqual(set(found), {"3"})

    def test_가시_링크와_href가_함께_바뀐다(self):
        """v2 템플릿은 가시 텍스트에 ?issue=2 가 하드코딩돼 있었다."""
        out2 = render(fixture.issue_data(7), fixture.template())
        self.assertEqual(set(re.findall(r"\?issue=(\d+)", out2["html"])), {"7"})

    def test_HTML_특수문자를_이스케이프한다(self):
        data = fixture.issue_data(3)
        data["headlines"][0]["title_ko"] = "A & B <스크립트>"
        out = render(data, fixture.template())
        self.assertIn("A &amp; B &lt;스크립트&gt;", out["html"])
        self.assertNotIn("<스크립트>", out["html"])

    def test_평문_대체본에_모든_항목이_들어간다(self):
        for item in self.data["headlines"]:
            self.assertIn(item["title_ko"], self.out["text"])

    def test_List_Unsubscribe_가_회신_스캔에_걸리는_형식이다(self):
        header = self.out["headers"]["List-Unsubscribe"]
        self.assertIn("mailto:", header)
        self.assertIn("subject=TCIM", header)

    def test_내부_주석이_발송본에_실리지_않는다(self):
        """템플릿 상단 주석은 배경색 제약을 적어 둔 내부 문서다. 구독자에게 갈 이유가 없다."""
        self.assertNotIn("<!--", self.out["html"])
        self.assertNotIn("render.py", self.out["html"])
        self.assertNotIn("CARD:START", self.out["html"])

    def test_주석을_떼어도_문서가_온전하다(self):
        self.assertTrue(self.out["html"].startswith("<!DOCTYPE html>"))
        self.assertTrue(self.out["html"].rstrip().endswith("</html>"))

    def test_날짜를_문자열로_줘도_된다(self):
        data = fixture.issue_data(3)
        data["period_start"] = "2026-08-03"
        out = render(data, fixture.template())
        self.assertIn("2026년 8월 3일", out["html"])


if __name__ == "__main__":
    unittest.main()
