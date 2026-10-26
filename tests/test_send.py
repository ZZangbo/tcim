"""발송 테스트. 네트워크를 타지 않는다 — transport 를 갈아끼운다."""

import unittest

import fixture
from tcim.render import render
from tcim.send import SendError, send_issue, send_one


class FakeTransport:
    """호출을 기록하고 정해진 응답을 돌려준다."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def __call__(self, url, payload, headers):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        if self.responses:
            nxt = self.responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return 200, {"id": f"msg_{len(self.calls)}"}


def rendered():
    return render(fixture.issue_data(3), fixture.template())


ARGS = dict(
    api_key="re_test",
    from_address="TCIM Global Watch <tcim@news.jbhlab.com>",
    reply_to="tcim@jbhlab.com",
    issue_no=3,
    sleep_seconds=0,
)


class TestPayload(unittest.TestCase):
    def test_수신자당_한_통씩_보낸다(self):
        t = FakeTransport()
        out = send_issue(rendered(), ["a@x.com", "b@y.com", "c@z.com"], transport=t, **ARGS)
        self.assertEqual(len(t.calls), 3)
        self.assertEqual(out["sent"], 3)

    def test_BCC_를_쓰지_않는다(self):
        """한 명씩 보내므로 다른 수신자의 주소가 실릴 자리가 없다."""
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com", "b@y.com"], transport=t, **ARGS)
        for call in t.calls:
            self.assertNotIn("bcc", call["payload"])
            self.assertEqual(len(call["payload"]["to"]), 1)

    def test_한_통에_자기_주소만_들어간다(self):
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com", "b@y.com"], transport=t, **ARGS)
        self.assertEqual(t.calls[0]["payload"]["to"], ["a@x.com"])
        self.assertEqual(t.calls[1]["payload"]["to"], ["b@y.com"])

    def test_발신과_회신_주소가_실린다(self):
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        p = t.calls[0]["payload"]
        self.assertEqual(p["from"], "TCIM Global Watch <tcim@news.jbhlab.com>")
        self.assertEqual(p["reply_to"], ["tcim@jbhlab.com"])

    def test_List_Unsubscribe_헤더가_실린다(self):
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        header = t.calls[0]["payload"]["headers"]["List-Unsubscribe"]
        self.assertIn("tcim@jbhlab.com", header)
        self.assertIn("subject=TCIM", header)

    def test_회신_주소와_구독취소_주소가_같다(self):
        """다르면 회신 스캔이 한쪽을 놓친다."""
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        p = t.calls[0]["payload"]
        self.assertIn(p["reply_to"][0], p["headers"]["List-Unsubscribe"])

    def test_평문과_HTML_을_둘_다_보낸다(self):
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        p = t.calls[0]["payload"]
        self.assertTrue(p["html"].startswith("<!DOCTYPE html>"))
        self.assertIn("TCIM Global Watch", p["text"])

    def test_인증_헤더(self):
        t = FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        self.assertEqual(t.calls[0]["headers"]["Authorization"], "Bearer re_test")


class TestIdempotency(unittest.TestCase):
    def test_같은_호_같은_주소는_같은_키를_쓴다(self):
        t1, t2 = FakeTransport(), FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t1, **ARGS)
        send_issue(rendered(), ["A@X.com"], transport=t2, **ARGS)
        self.assertEqual(
            t1.calls[0]["headers"]["Idempotency-Key"],
            t2.calls[0]["headers"]["Idempotency-Key"],
        )

    def test_호가_다르면_키가_다르다(self):
        t1, t2 = FakeTransport(), FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t1, **{**ARGS, "issue_no": 3})
        send_issue(rendered(), ["a@x.com"], transport=t2, **{**ARGS, "issue_no": 4})
        self.assertNotEqual(
            t1.calls[0]["headers"]["Idempotency-Key"],
            t2.calls[0]["headers"]["Idempotency-Key"],
        )


    def test_정정판은_키가_다르다(self):
        """revision 이 키에 없으면 정정판이 Resend 에서 조용히 걸러진다."""
        t1, t2 = FakeTransport(), FakeTransport()
        send_issue(rendered(), ["a@x.com"], transport=t1, **ARGS)
        send_issue(rendered(), ["a@x.com"], transport=t2, revision=2, **ARGS)
        self.assertNotEqual(
            t1.calls[0]["headers"]["Idempotency-Key"],
            t2.calls[0]["headers"]["Idempotency-Key"],
        )

    def test_1판은_기존_키_형식을_유지한다(self):
        """이미 나간 호와의 중복 방어가 끊기지 않아야 한다."""
        from tcim.send import _idempotency_key
        self.assertRegex(_idempotency_key(3, "a@x.com"), r"^tcim-3-[0-9a-f]{16}$")
        self.assertEqual(_idempotency_key(3, "a@x.com"), _idempotency_key(3, "a@x.com", 1))


class TestFailure(unittest.TestCase):
    def test_한_명이_실패해도_나머지는_나간다(self):
        t = FakeTransport([(422, {"message": "잘못된 주소"}), (200, {"id": "ok"})])
        out = send_issue(rendered(), ["bad@x", "good@y.com"], transport=t, **ARGS)
        self.assertEqual(out["sent"], 1)
        self.assertEqual(out["failed"], 1)
        self.assertEqual(out["results"][0]["status"], "failed")
        self.assertIn("422", out["results"][0]["error"])

    def test_4xx_는_재시도하지_않는다(self):
        """주소 오류나 도메인 미검증은 다시 보내도 같은 결과다."""
        t = FakeTransport([(403, {"message": "도메인 미검증"})])
        send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        self.assertEqual(len(t.calls), 1)

    def test_429_는_재시도한다(self):
        t = FakeTransport([(429, {"message": "rate limited"}), (200, {"id": "ok"})])
        out = send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        self.assertEqual(out["sent"], 1)
        self.assertEqual(len(t.calls), 2)

    def test_5xx_도_재시도한다(self):
        t = FakeTransport([(503, {}), (503, {}), (200, {"id": "ok"})])
        out = send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        self.assertEqual(out["sent"], 1)

    def test_계속_실패하면_실패로_남는다(self):
        t = FakeTransport([(503, {}), (503, {}), (503, {})])
        out = send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        self.assertEqual(out["failed"], 1)

    def test_네트워크_예외를_삼킨다(self):
        t = FakeTransport([SendError("연결 실패"), (200, {"id": "ok"})])
        out = send_issue(rendered(), ["a@x.com"], transport=t, **ARGS)
        self.assertEqual(out["sent"], 1)


class TestResume(unittest.TestCase):
    def test_이미_보낸_사람은_건너뛴다(self):
        t = FakeTransport()
        out = send_issue(
            rendered(), ["a@x.com", "b@y.com"], already_sent={"A@X.COM"}, transport=t, **ARGS
        )
        self.assertEqual(len(t.calls), 1)
        self.assertEqual(t.calls[0]["payload"]["to"], ["b@y.com"])
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(out["sent"], 1)


class TestDryRun(unittest.TestCase):
    def test_dry_run_은_한_통도_보내지_않는다(self):
        t = FakeTransport()
        out = send_issue(rendered(), ["a@x.com", "b@y.com"], dry_run=True, transport=t, **ARGS)
        self.assertEqual(len(t.calls), 0)
        self.assertEqual(out["skipped"], 2)
        self.assertTrue(out["dry_run"])

class TestTransportHeaders(unittest.TestCase):
    """실제 HTTP 계층. api.resend.com 이 Cloudflare 뒤에 있어 UA 가 없으면 403 이 온다."""

    def test_기본_UA_로는_요청하지_않는다(self):
        import urllib.request

        from tcim import send as send_mod

        captured = {}

        class FakeResp:
            status = 200

            def read(self):
                return b'{"id":"x"}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            captured["ua"] = req.get_header("User-agent")
            return FakeResp()

        original = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            send_mod._http_post("https://api.resend.com/emails", {}, {"Authorization": "Bearer x"})
        finally:
            urllib.request.urlopen = original

        self.assertTrue(captured["ua"])
        self.assertNotIn("urllib", captured["ua"].lower())

if __name__ == "__main__":
    unittest.main()
