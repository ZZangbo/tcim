"""발행 계획 테스트.

날짜는 실제 회차의 값을 쓴다. 제2호 period_end 가 2026-08-02 였고
그다음 발행은 2026-08-17 이어야 한다.
"""

import unittest
from datetime import date

from tcim.plan import make_plan


class TestGuard(unittest.TestCase):
    """격주 가드. 매주 깨어나되 발행은 2주에 한 번이다."""

    def test_발행_다음날_실행은_건너뛴다(self):
        # 실제로 2026-08-03 실행에서 일어난 일이다
        r = make_plan(date(2026, 8, 3), date(2026, 8, 2), 2)
        self.assertFalse(r["should_publish"])
        self.assertEqual(r["reason"], "격주 주기 — 이번 주는 건너뜀")
        self.assertEqual(r["days_since_last"], 1)

    def test_쉬는_주에는_알리지_않는다(self):
        r = make_plan(date(2026, 8, 3), date(2026, 8, 2), 2)
        self.assertFalse(r["notify"])

    def test_한_주_뒤에도_아직_건너뛴다(self):
        r = make_plan(date(2026, 8, 10), date(2026, 8, 2), 2)
        self.assertFalse(r["should_publish"])
        self.assertEqual(r["days_since_last"], 8)

    def test_두_주_뒤에_발행한다(self):
        r = make_plan(date(2026, 8, 17), date(2026, 8, 2), 2)
        self.assertTrue(r["should_publish"])
        self.assertEqual(r["reason"], "정상 주기")
        self.assertEqual(r["days_since_last"], 15)

    def test_다음_발행일을_알려준다(self):
        for today in (date(2026, 8, 3), date(2026, 8, 10)):
            with self.subTest(today=today):
                r = make_plan(today, date(2026, 8, 2), 2)
                self.assertEqual(r["next_publish"], "2026-08-17")

    def test_실행이_하루_밀려도_주기가_밀리지_않는다(self):
        """13일로 잡은 이유. 14일이면 몇 분 차이로 한 주를 통째로 걸렀을 것이다."""
        r = make_plan(date(2026, 8, 16), date(2026, 8, 2), 2)
        self.assertTrue(r["should_publish"])
        self.assertEqual(r["days_since_last"], 14)


class TestPeriod(unittest.TestCase):
    def test_수집_기간은_직전_종료_다음날부터_어제까지(self):
        r = make_plan(date(2026, 8, 17), date(2026, 8, 2), 2)
        self.assertEqual(r["period_start"], "2026-08-03")
        self.assertEqual(r["period_end"], "2026-08-16")
        self.assertEqual(r["period_days"], 14)

    def test_issue_no_는_직전_더하기_일(self):
        r = make_plan(date(2026, 8, 17), date(2026, 8, 2), 2)
        self.assertEqual(r["issue_no"], 3)

    def test_week_no_는_period_end_기준_ISO_주(self):
        r = make_plan(date(2026, 8, 17), date(2026, 8, 2), 2)
        expected = "{}-W{:02d}".format(*date(2026, 8, 16).isocalendar()[:2])
        self.assertEqual(r["week_no"], expected)

    def test_첫_발행은_최근_14일(self):
        r = make_plan(date(2026, 7, 13), None, None)
        self.assertTrue(r["should_publish"])
        self.assertEqual(r["reason"], "최초 발행")
        self.assertEqual(r["period_days"], 14)
        self.assertEqual(r["issue_no"], 0)
        self.assertEqual(r["period_end"], "2026-07-12")


class TestBackfill(unittest.TestCase):
    """한 회차가 실패해도 다음 회차가 빠진 구간을 통째로 이어받는다."""

    def test_정상_주기는_백필이_아니다(self):
        r = make_plan(date(2026, 8, 17), date(2026, 8, 2), 2)
        self.assertFalse(r["backfill"])

    def test_한_회차를_거르면_백필로_표시한다(self):
        # 8/17 실행이 실패하고 8/24 에 이어받는 상황
        r = make_plan(date(2026, 8, 24), date(2026, 8, 2), 2)
        self.assertTrue(r["should_publish"])
        self.assertTrue(r["backfill"])
        self.assertEqual(r["period_start"], "2026-08-03")
        self.assertEqual(r["period_end"], "2026-08-23")
        self.assertEqual(r["period_days"], 21)

    def test_백필_회차도_issue_no_는_하나만_증가한다(self):
        """결번을 만들지 않고 빠진 구간을 한 호로 합친다."""
        r = make_plan(date(2026, 8, 24), date(2026, 8, 2), 2)
        self.assertEqual(r["issue_no"], 3)


class TestDefensive(unittest.TestCase):
    def test_이미_커버된_기간은_발행하지_않는다(self):
        """현재 가드 설정에서는 도달하지 않는 분기다. 가드를 낮출 때를 위한 방어다."""
        from tcim import plan as plan_mod

        original = plan_mod.GUARD_DAYS
        plan_mod.GUARD_DAYS = -10  # 직전 종료일이 미래라 days_since 가 음수다
        try:
            r = make_plan(date(2026, 8, 3), date(2026, 8, 5), 2)
            self.assertFalse(r["should_publish"])
            self.assertEqual(r["reason"], "신규 기간 없음")
            self.assertTrue(r["notify"])  # 이건 조용히 넘기면 안 된다
        finally:
            plan_mod.GUARD_DAYS = original


if __name__ == "__main__":
    unittest.main()
