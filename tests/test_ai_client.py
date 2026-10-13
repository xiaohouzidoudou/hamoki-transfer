import io
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1] / "integrations" / "hamoki-private-ai"
sys.path.insert(0,str(ROOT))
from run import HamokiClient, HamokiError

class AiClientTests(unittest.TestCase):
    def setUp(self):
        self.client=HamokiClient(base_url="https://example.com",token="hka_"+"a"*64)

    def test_https_and_token_required(self):
        with self.assertRaises(HamokiError):
            HamokiClient(base_url="http://example.com",token="hka_"+"a"*64)
        with self.assertRaises(HamokiError):
            HamokiClient(base_url="https://example.com",token="bad")

    def test_send_text_and_latest_contract(self):
        with patch.object(self.client,"request",return_value={"ok":True}) as request:
            result=self.client.send_text("测试AI同步")
            self.assertTrue(result["ok"])
            self.assertEqual(result["kind"],"text")
            self.assertEqual(request.call_args.args[0],"/api/private/send")
            self.assertIn(b"%E6%B5%8B",request.call_args.args[1])
        with patch.object(self.client,"request",return_value={"text":"latest"}) as request:
            self.assertEqual(self.client.get_latest()["text"],"latest")
            self.assertEqual(request.call_args.args,("/api/private/latest",))
        with self.assertRaises(HamokiError): self.client.send_text("")

    def test_file_upload_stream_contract(self):
        class FakeResponse:
            status=201
            def read(self,limit):return b'{"ok":true}'
        class FakeConn:
            def __init__(self,*args,**kwargs):self.headers={};self.chunks=[]
            def putrequest(self,method,path):self.method=method;self.path=path
            def putheader(self,key,val):self.headers[key]=val
            def endheaders(self):pass
            def send(self,data):self.chunks.append(data)
            def getresponse(self):return FakeResponse()
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            filename=Path(directory)/"mytest.txt";filename.write_bytes(b"hello-ai")
            conn=FakeConn()
            with patch("run.http.client.HTTPSConnection",return_value=conn):
                result=self.client.send_file(str(filename))
            self.assertTrue(result["ok"])
            self.assertEqual(result["name"],"mytest.txt")
            self.assertEqual(conn.method,"POST")
            self.assertEqual(conn.path,"/api/private/send")
            self.assertEqual(int(conn.headers["Content-Length"]),sum(map(len,conn.chunks)))
            self.assertIn(b"hello-ai",b"".join(conn.chunks))
            (Path(directory)/"secret.key").write_text("no")
            with self.assertRaises(HamokiError):
                self.client.send_file(str(Path(directory)/"secret.key"))

    def test_mcp_stdio_initialize_and_tool_listing(self):
        requests=[
            {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26"}},
            {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},
        ]
        result=subprocess.run([sys.executable,str(ROOT/"mcp_server.py")],
            input="\n".join(json.dumps(r) for r in requests)+"\n",text=True,
            capture_output=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        messages=[json.loads(line) for line in result.stdout.strip().splitlines()]
        self.assertEqual(messages[0]["result"]["serverInfo"]["name"],"hamoki-private-ai")
        self.assertEqual({tool["name"] for tool in messages[1]["result"]["tools"]},
                         {"send_text","send_file","get_latest"})

if __name__=="__main__":
    unittest.main()
