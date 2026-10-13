import io
import tempfile
import unittest
from pathlib import Path

from app import RATE, RATE_LOCK, create_app


class PrivateHistoryTests(unittest.TestCase):
    def setUp(self):
        with RATE_LOCK:
            RATE.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.config = {"TESTING": True, "DATA_DIR": self.tmp.name, "TOTAL_BYTES": 10}
        self.app = create_app(self.config)
        self.pc = self.app.test_client()
        self.phone = self.app.test_client()
        self.other = self.app.test_client()
        self.headers = {"X-Hamoki-Client": "1"}
        self.assertEqual(
            self.pc.post("/api/private/create", json={"label": "电脑"}, headers=self.headers).status_code,
            201
        )
        invite = self.pc.get("/api/private/invite").json["invite"]
        self.assertEqual(self.phone.post("/api/private/join",
                         json={"invite": invite, "label": "手机"}, headers=self.headers).status_code, 200)

    def tearDown(self):
        self.tmp.cleanup()

    def send_text(self, client, value):
        return client.post("/api/private/send", data={"text": value}, headers=self.headers)

    def send_file(self, client, value, name):
        return client.post("/api/private/send",
                           data={"file": (io.BytesIO(value), name)},
                           headers=self.headers, content_type="multipart/form-data")

    def history(self, client):
        return client.get("/api/private/history")

    def test_two_previous_text_items_and_restart(self):
        self.assertEqual(self.history(self.phone).json["items"], [])
        self.send_text(self.pc, "第一条")
        self.assertEqual(self.history(self.phone).json["items"], [])
        self.send_text(self.pc, "第二条")
        self.assertEqual([i["text"] for i in self.history(self.phone).json["items"]], ["第一条"])
        self.send_text(self.phone, "第三条")
        self.assertEqual([i["text"] for i in self.history(self.phone).json["items"]], ["第二条", "第一条"])
        self.send_text(self.pc, "第四条")
        self.assertEqual(self.phone.get("/api/private/latest").json["text"], "第四条")
        self.assertEqual([i["text"] for i in self.history(self.phone).json["items"]], ["第三条", "第二条"])
        self.assertEqual(len(self.history(self.phone).json["items"]), 2)
        cookie = self.pc.get_cookie("hamoki_private_device").value
        another_app = create_app(self.config)
        another_client = another_app.test_client()
        another_client.set_cookie("hamoki_private_device", cookie)
        self.assertEqual([i["text"] for i in self.history(another_client).json["items"]],
                         ["第三条", "第二条"])

    def test_private_file_history_download_pruning_and_quota(self):
        self.assertEqual(self.send_file(self.pc, b"aaaa", "a.txt").status_code, 201)
        self.assertEqual(self.send_file(self.pc, b"bbbb", "b.txt").status_code, 201)
        first = self.history(self.phone).json["items"][0]
        self.assertEqual(first["filename"], "a.txt")
        route = "/api/private/history/file/" + first["id"]
        self.assertEqual(self.phone.get(route).data, b"aaaa")
        self.assertIn("attachment", self.phone.get(route).headers["Content-Disposition"])
        # Retained old files must count against the 10 byte total limit.
        failed = self.send_file(self.pc, b"cccc", "c.txt")
        self.assertEqual(failed.status_code, 507)
        self.assertEqual(self.phone.get("/api/private/latest").json["filename"], "b.txt")
        self.assertEqual(self.send_file(self.pc, b"cc", "c.txt").status_code, 201)
        hist = self.history(self.phone).json["items"]
        self.assertEqual([i["filename"] for i in hist], ["b.txt", "a.txt"])
        self.assertEqual(self.send_file(self.phone, b"dddd", "d.txt").status_code, 201)
        hist = self.history(self.pc).json["items"]
        self.assertEqual([i["filename"] for i in hist], ["c.txt", "b.txt"])
        self.assertEqual(self.phone.get(route).status_code, 404)
        self.assertEqual(self.phone.get("/api/private/history/file/" + hist[0]["id"]).data, b"cc")
        self.assertEqual(len(list((Path(self.tmp.name) / "private-files").glob("*"))), 3)
        self.assertEqual(self.phone.get("/api/private/file").data, b"dddd")

    def test_unpaired_and_other_room_cannot_view_history(self):
        self.send_text(self.pc, "secret A")
        self.send_text(self.pc, "secret B")
        entry = self.history(self.phone).json["items"][0]
        self.assertEqual(self.other.get("/api/private/history").status_code, 401)
        self.assertEqual(self.other.get("/api/private/history/file/" + entry["id"]).status_code, 401)
        self.assertEqual(self.other.post("/api/private/create",
                                         json={"label":"其他房间"},headers=self.headers).status_code,201)
        self.assertEqual(self.history(self.other).json["items"],[])
        self.assertEqual(self.other.get("/api/private/history/file/" + entry["id"]).status_code,404)
        self.assertEqual(self.phone.get("/api/private/history/file/not-valid").status_code,404)

    def test_agent_send_creates_history_without_clearing_last(self):
        self.send_text(self.pc, "手机要复制第一段")
        resp=self.pc.post("/api/private/agent/create",
                          json={"label":"公司 AI"},headers=self.headers)
        self.assertEqual(resp.status_code,201)
        token=resp.json["token"]
        agent=self.app.test_client()
        sent=agent.post("/api/private/send",data={"text":"AI 新文字"},
                        headers={**self.headers,"Authorization":"Bearer "+token})
        self.assertEqual(sent.status_code,201)
        self.assertEqual(self.phone.get("/api/private/latest").json["text"],"AI 新文字")
        prior=self.history(self.phone).json["items"]
        self.assertEqual(prior[0]["text"],"手机要复制第一段")
        self.assertEqual(prior[0]["sender"],"电脑")

    def test_ui_has_copy_buttons_and_new_history_fetch(self):
        html=self.pc.get("/").data.decode("utf-8")
        self.assertIn('id="private-history-section"',html)
        self.assertIn('id="private-history-list"',html)
        js=(Path(__file__).resolve().parents[1] / "static" / "private.js").read_text(encoding="utf-8")
        self.assertIn("api('history')",js)
        self.assertIn("navigator.clipboard.writeText(item.text)",js)
        self.assertIn("api/private/history/file/",js)


if __name__=="__main__":
    unittest.main()
