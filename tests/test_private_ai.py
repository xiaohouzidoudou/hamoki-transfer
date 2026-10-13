import io
import tempfile
import unittest
from pathlib import Path
from app import RATE, RATE_LOCK, create_app


class PrivateAgentTests(unittest.TestCase):
    def setUp(self):
        with RATE_LOCK:
            RATE.clear()
        self.folder=tempfile.TemporaryDirectory()
        self.app=create_app({"TESTING":True,"DATA_DIR":self.folder.name})
        self.web=self.app.test_client()
        self.ai=self.app.test_client()
        self.headers={"X-Hamoki-Client":"1"}
        made=self.web.post("/api/private/create",json={"label":"我的电脑"},headers=self.headers)
        self.assertEqual(made.status_code,201)
        self.invite=made.json["invite"]

    def tearDown(self):
        self.folder.cleanup()

    def create_agent(self):
        r=self.web.post("/api/private/agent/create",json={"label":"我的 AgentDock"},headers=self.headers)
        self.assertEqual(r.status_code,201,r.json)
        return r.json

    def test_issue_send_read_file_revoke(self):
        info=self.create_agent()
        token=info["token"]
        self.assertRegex(token,r"^hka_[a-f0-9]{64}$")
        agent_headers={**self.headers,"Authorization":"Bearer "+token}
        self.assertEqual(self.ai.post("/api/private/send",headers=agent_headers,data={"text":"来自AI的文字"}).status_code,201)
        got=self.web.get("/api/private/latest").json
        self.assertEqual(got["text"],"来自AI的文字")
        self.assertEqual(got["sender"],"我的 AgentDock")
        self.assertEqual(self.ai.get("/api/private/latest",headers=agent_headers).json["text"],"来自AI的文字")
        sent=self.ai.post("/api/private/send",headers=agent_headers,
                data={"file":(io.BytesIO(b"ai-test"),"result.txt")},
                content_type="multipart/form-data")
        self.assertEqual(sent.status_code,201,sent.json)
        self.assertEqual(self.web.get("/api/private/file").data,b"ai-test")
        self.assertEqual(self.ai.get("/api/private/file",headers=agent_headers).data,b"ai-test")
        self.assertEqual(self.web.post("/api/private/agent/revoke",json={"id":info["id"]},headers=self.headers).status_code,200)
        self.assertEqual(self.ai.get("/api/private/latest",headers=agent_headers).status_code,401)
        self.assertEqual(self.web.get("/api/private/latest").status_code,200)

    def test_scoped_token_cannot_control_room(self):
        info=self.create_agent()
        headers={**self.headers,"Authorization":"Bearer "+info["token"]}
        blocked=[
            ("get","/api/private/devices",None),
            ("get","/api/private/invite",None),
            ("get","/api/private/agent/list",None),
            ("post","/api/private/agent/create",{"label":"偷来的AI"}),
            ("post","/api/private/invite/reissue",{}),
            ("post","/api/private/agent/revoke",{"id":info["id"]}),
        ]
        for method,path,payload in blocked:
            response=getattr(self.ai,method)(path,headers=headers,**({"json":payload} if payload is not None else {}))
            self.assertEqual(response.status_code,401,(path,response.json))
        self.assertEqual(self.web.get("/api/private/agent/list").json["agents"][0]["label"],"我的 AgentDock")
        self.assertNotIn("token",str(self.web.get("/api/private/agent/list").json))

    def test_unpaired_cannot_issue_tokens(self):
        response=self.ai.post("/api/private/agent/create",headers=self.headers,json={"label":"陌生人"})
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.web.post("/api/private/agent/create",json={"label":"AI"}).status_code,403)
        self.assertEqual(self.ai.get("/api/private/latest",headers={"Authorization":"Bearer hka_"+"0"*64}).status_code,401)
        self.assertEqual(self.ai.get("/api/private/latest").status_code,401)

    def test_autopaste_interface(self):
        page=self.web.get("/").data.decode()
        self.assertIn('id="private-agent-create"',page)
        self.assertIn('id="private-agent-list"',page)
        self.assertIn('粘贴文字即自动发送',page)
        script=(Path(__file__).resolve().parents[1]/"static/private.js").read_text()
        self.assertIn("addEventListener('paste'",script)
        self.assertIn("el('private-send').click()",script)
        self.assertIn("chosenFiles.length)return",script)


if __name__=="__main__":
    unittest.main()
