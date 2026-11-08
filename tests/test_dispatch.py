"""세션 밖 발송기 테스트. Supabase 와 Resend 를 모두 가짜로 갈아끼운다."""

import unittest
from datetime import datetime, timedelta, timezone

import fixture
from tcim import dispatch

NOW = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)


def job_payload():
    data = fixture.issue_data(9)
    data.pop("recipients")
    data.pop("issue_no")
    return data


class FakeDB:
    def __init__(self, approved, sent=(), config=None, jobs=None):
        self.approved = list(approved)
        self.sent = list(sent)
        self.config = config if config is not None else {
            "resend_api_key": "re_test",
            "mail_from": "TCIM Global Watch <tcim@news.jbhlab.com>",
            "mail_reply_to": "tcim@jbhlab.com",
            "auto_send": "true",
        }
        self.jobs = jobs if jobs is not None else [
            {"issue_no": 9, "revision": 1, "payload": job_payload(),
             "created_at": (NOW - timedelta(hours=1)).isoformat()}
        ]
        self.rpcs = []

    def select(self, table, query):
        if table == "tcim_mail_jobs":
            rows = sorted(self.jobs, key=lambda j: (j["issue_no"], j["revision"]), reverse=True)
            if "issue_no=eq." in query:
                n = int(query.split("issue_no=eq.")[1].split("&")[0])
                rows = [j for j in rows if j["issue_no"] == n]
            return rows[:1]
        if table == "tcim_subscribers":
            return [{"email": e} for e in self.approved]
        if table == "tcim_sends":
            return [{"email": e} for e in self.sent]
        if table == "tcim_private_config":
            return [{"key": k, "value": v} for k, v in self.config.items()]
        raise AssertionError(table)

    def rpc(self, fn, args):
        self.rpcs.append((fn, args))
        return len(args["p_results"])


class FakeTransport:
    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, url, payload, headers):
        self.calls.append(payload["to"][0])
        if payload["to"][0] in self.fail:
            return 422, {"message": "invalid"}
        return 200, {"id": f"msg_{len(self.calls)}"}


def run(db, **kw):
    t = kw.pop("transport", None) or FakeTransport()
    out = dispatch.run(db, fixture.template(), now=NOW, transport=t, sleep_seconds=0, **kw)
    return out, t


APPROVED = ["a@example.com", "b@example.com", "c@example.com"]


class TestDispatch(unittest.TestCase):
    def test_sends_to_everyone_and_records(self):
        db = FakeDB(APPROVED)
        out, t = run(db)
        self.assertTrue(out["ok"])
        self.assertEqual(out["sent"], 3)
        self.assertEqual(t.calls, APPROVED)
        fn, args = db.rpcs[0]
        self.assertEqual(fn, "tcim_record_sends")
        self.assertEqual((args["p_issue"], args["p_revision"]), (9, 1))
        self.assertEqual(len(args["p_results"]), 3)

    def test_skips_already_sent_and_does_not_record_skips(self):
        db = FakeDB(APPROVED, sent=["A@example.com"])
        out, t = run(db)
        self.assertEqual(t.calls, ["b@example.com", "c@example.com"])
        recorded = [r["email"] for r in db.rpcs[0][1]["p_results"]]
        self.assertNotIn("a@example.com", recorded)

    def test_all_sent_is_noop(self):
        db = FakeDB(APPROVED, sent=APPROVED)
        out, t = run(db)
        self.assertEqual(out["action"], "none")
        self.assertEqual(t.calls, [])
        self.assertEqual(db.rpcs, [])

    def test_recipients_come_from_db_not_payload(self):
        db = FakeDB(APPROVED)
        db.jobs[0]["payload"]["recipients"] = ["stale@example.com"]
        out, t = run(db)
        self.assertEqual(t.calls, APPROVED)

    def test_preflight_failure_sends_nothing(self):
        db = FakeDB(APPROVED)
        db.jobs[0]["payload"]["headlines"] = db.jobs[0]["payload"]["headlines"][:1]
        out, t = run(db)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "프리플라이트 실패")
        self.assertEqual(t.calls, [])
        self.assertEqual(db.rpcs, [])

    def test_auto_send_off_is_dry_run(self):
        db = FakeDB(APPROVED)
        db.config["auto_send"] = "false"
        out, t = run(db)
        self.assertEqual(out["action"], "dry_run")
        self.assertEqual(t.calls, [])
        self.assertEqual(db.rpcs, [])

    def test_failure_marks_not_ok_and_is_recorded(self):
        db = FakeDB(APPROVED)
        out, _ = run(db, transport=FakeTransport(fail={"b@example.com"}))
        self.assertFalse(out["ok"])
        self.assertEqual(out["failed"], ["b@example.com"])
        statuses = {r["email"]: r["status"] for r in db.rpcs[0][1]["p_results"]}
        self.assertEqual(statuses["b@example.com"], "failed")

    def test_old_job_is_ignored_by_cron_but_not_by_manual_issue(self):
        db = FakeDB(APPROVED)
        db.jobs[0]["created_at"] = (NOW - timedelta(days=11)).isoformat()
        out, t = run(db)
        self.assertEqual(out["action"], "none")
        out, t = run(db, issue_no=9)
        self.assertEqual(out["sent"], 3)

    def test_missing_api_key_blocks(self):
        db = FakeDB(APPROVED)
        del db.config["resend_api_key"]
        out, t = run(db)
        self.assertFalse(out["ok"])
        self.assertEqual(t.calls, [])

    def test_no_job(self):
        db = FakeDB(APPROVED, jobs=[])
        out, _ = run(db)
        self.assertEqual(out["action"], "none")

    def test_supabase_requires_credentials(self):
        with self.assertRaises(dispatch.DispatchError):
            dispatch.Supabase("", "")


if __name__ == "__main__":
    unittest.main()
