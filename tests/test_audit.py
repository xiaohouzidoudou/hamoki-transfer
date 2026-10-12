import tempfile
import time
import unittest

from app import RATE, RATE_LOCK, create_app


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        with RATE_LOCK: RATE.clear()
        self.tmp=tempfile.TemporaryDirectory()
        self.conf={"TESTING":True,"DATA_DIR":self.tmp.name,
                   "UPLOAD_UNLOCK_PASSWORD":"owner-test-password",
                   "TOTAL_BYTES":4096}
        self.app=create_app(self.conf)
        self.client=self.app.test_client()
        self.day=int(time.time())//86400*86400

    def tearDown(self): self.tmp.cleanup()

    def url(self, name):
        return "/api/admin/"+name+"?from="+str(self.day)+"&to="+str(self.day+86400)

    def login(self, client=None):
        return (client or self.client).post("/api/admin/login",
          json={"password":"owner-test-password"},headers={"X-Hamoki-Client":"1"})

    def test_secret_required_for_all_log_data(self):
        self.assertEqual(self.client.get("/admin/logs").status_code,200)
        self.assertEqual(self.client.get(self.url("events")).status_code,401)
        self.assertEqual(self.client.get(self.url("summary")).status_code,401)
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"owner-test-password"}).status_code,403)
        self.assertEqual(self.client.post("/api/admin/login",json={"password":"wrong"},headers={"X-Hamoki-Client":"1"}).status_code,403)
        self.assertEqual(self.login().status_code,200)
        self.assertTrue(self.client.get("/api/admin/session").json["authenticated"])
        other=self.app.test_client()
        self.assertEqual(other.get(self.url("events")).status_code,401)
        self.assertEqual(self.client.post("/api/admin/logout",headers={"X-Hamoki-Client":"1"}).status_code,200)
        self.assertEqual(self.client.get(self.url("events")).status_code,401)

    def test_actions_ip_failures_and_secrets_not_logged(self):
        self.client.get("/")
        response=self.client.post("/api/send",data={"text":"private-text-payload","ttl":"1h"},
                  environ_overrides={"REMOTE_ADDR":"198.51.100.2"})
        self.assertEqual(response.status_code,201)
        self.client.get("/notfound/my-private-token?password=very-secret")
        self.assertEqual(self.login().status_code,200)
        events=self.client.get(self.url("events")).json["events"]
        actions={row["action"] for row in events}
        self.assertTrue({"访问首页","公开上传","可疑路径"}.issubset(actions))
        sent=next(row for row in events if row["action"]=="公开上传")
        self.assertEqual(sent["ip"],"198.51.100.2")
        self.assertEqual(sent["status"],201)
        payload=str(events)
        for secret in ("private-text-payload","my-private-token","very-secret",response.json["code"]):
            self.assertNotIn(secret,payload)
        summary=self.client.get(self.url("summary")).json
        self.assertGreaterEqual(summary["totals"]["requests"],3)
        self.assertGreaterEqual(summary["totals"]["failures"],1)

    def test_device_name_and_code_privacy(self):
        result=self.client.post("/api/private/create",json={"label":"我的电脑"},
             headers={"X-Hamoki-Client":"1"})
        self.assertEqual(result.status_code,201)
        self.client.get("/api/private/file")
        self.assertEqual(self.login().status_code,200)
        events=self.client.get(self.url("events")).json["events"]
        self.assertTrue(any(row["action"]=="创建私人空间" for row in events))
        self.assertTrue(any(row["device"]=="我的电脑" for row in events))
        self.assertNotIn(result.json["invite"],str(events))

    def test_ui_bad_range_and_disabled_login(self):
        page=self.client.get("/admin/logs")
        self.assertIn(b'id="audit-password"',page.data)
        self.assertIn(b'id="audit-rows"',page.data)
        self.assertEqual(self.login().status_code,200)
        self.assertEqual(self.client.get("/api/admin/events?from=1&to=1").status_code,400)
        disabled=create_app({**self.conf,"UPLOAD_UNLOCK_PASSWORD":""}).test_client()
        self.assertEqual(disabled.post("/api/admin/login",json={"password":""},
                    headers={"X-Hamoki-Client":"1"}).status_code,403)


if __name__=="__main__": unittest.main()
