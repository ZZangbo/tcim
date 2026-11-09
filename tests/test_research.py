"""'이번 호 주요 연구' 절 테스트. 렌더와 프리플라이트를 함께 본다."""

import unittest

import fixture
from tcim.preflight import check
from tcim.render import render


def data_with(research):
    data = fixture.issue_data(9)
    data["research"] = research
    return data


class TestRender(unittest.TestCase):
    def test_연구_수만큼_DOI_링크가_실린다(self):
        r = render(data_with(fixture.research_items()), fixture.template())
        self.assertEqual(r["html"].count(">DOI 보기</a>"), 3)
        for item in fixture.research_items():
            self.assertIn(item["url"], r["html"])
            self.assertIn(item["title_ko"], r["html"])

    def test_절_제목이_있다(self):
        r = render(data_with(fixture.research_items()), fixture.template())
        self.assertIn("이번 호 주요 연구", r["html"])

    def test_연구가_없으면_절째_빠진다(self):
        r = render(fixture.issue_data(9), fixture.template())
        self.assertNotIn("이번 호 주요 연구", r["html"])
        self.assertNotIn("DOI 보기", r["html"])
        self.assertNotIn("{{R_", r["html"])
        self.assertNotIn("이번 호 주요 연구", r["text"])

    def test_자리표시자와_표시가_남지_않는다(self):
        r = render(data_with(fixture.research_items()), fixture.template())
        self.assertNotIn("{{", r["html"])
        self.assertNotIn("RITEM", r["html"])
        self.assertNotIn("RESEARCH:", r["html"])

    def test_출처에_가운뎃점을_쓰지_않는다(self):
        r = render(data_with(fixture.research_items()), fixture.template())
        self.assertIn("PLoS Med, 2026", r["html"])
        self.assertNotIn("·", r["html"].split("이번 호 주요 연구", 1)[1].split("전체 보기", 1)[0])

    def test_평문에_DOI가_실린다(self):
        r = render(data_with(fixture.research_items()), fixture.template())
        self.assertIn("이번 호 주요 연구", r["text"])
        self.assertIn("DOI: https://doi.org/10.1371/journal.pmed.1005273", r["text"])

    def test_URL과_제목을_이스케이프한다(self):
        items = fixture.research_items()
        items[0]["title_ko"] = "A <b> & B"
        items[0]["url"] = 'https://doi.org/10.1/x"onmouseover="y'
        r = render(data_with(items), fixture.template())
        self.assertIn("A &lt;b&gt; &amp; B", r["html"])
        self.assertNotIn('"onmouseover="', r["html"])


class TestPreflight(unittest.TestCase):
    def run_check(self, research):
        data = data_with(research)
        return check(render(data, fixture.template()), data, approved_count=4)

    def test_정상은_통과(self):
        r = self.run_check(fixture.research_items())
        self.assertTrue(r["ok"], r["failures"])
        self.assertEqual(r["checked"], 14)

    def test_없으면_경고만(self):
        r = self.run_check([])
        self.assertTrue(r["ok"], r["failures"])
        self.assertTrue(any("주요 연구" in w for w in r["warnings"]))

    def test_6편이면_실패(self):
        items = (fixture.research_items() * 2)[:6]
        r = self.run_check(items)
        self.assertFalse(r["ok"])

    def test_저널명이_없으면_실패(self):
        items = fixture.research_items()
        items[1]["journal"] = ""
        self.assertFalse(self.run_check(items)["ok"])

    def test_요약이_짧으면_실패(self):
        items = fixture.research_items()
        items[0]["summary_ko"] = "짧음"
        self.assertFalse(self.run_check(items)["ok"])

    def test_https가_아니면_실패(self):
        items = fixture.research_items()
        items[2]["url"] = "10.1186/s12906-026-05494-0"
        self.assertFalse(self.run_check(items)["ok"])

    def test_DOI가_아닌_https는_경고(self):
        items = fixture.research_items()
        items[2]["url"] = "https://pubmed.ncbi.nlm.nih.gov/42880975/"
        r = self.run_check(items)
        self.assertTrue(r["ok"], r["failures"])
        self.assertTrue(any("DOI 주소가 아니다" in w for w in r["warnings"]))

    def test_기존_검사도_그대로_돈다(self):
        r = self.run_check(fixture.research_items())
        self.assertFalse(any("맨 URL" in f for f in r["failures"]))


if __name__ == "__main__":
    unittest.main()
