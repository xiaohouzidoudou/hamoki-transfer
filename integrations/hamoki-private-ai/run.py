#!/usr/bin/env python3
"""AI private transfer client: JSON instructions in stdin; no token in arguments."""
from __future__ import annotations
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request

MAX_SIZE=5*1024**3
TOKEN=re.compile(r"^hka_[0-9a-f]{64}$")
SENSITIVE={".env","id_rsa","id_ed25519","credentials.json","secrets.json"}
BLOCKED={".pem",".key",".p12",".pfx",".kdbx"}

class HamokiError(Exception):
    pass

class HamokiClient:
    def __init__(self,base_url=None,token=None):
        url=(base_url if base_url is not None else os.environ.get("HAMOKI_BASE_URL","")).rstrip("/")
        parsed=urllib.parse.urlsplit(url)
        if (parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ("","/") or parsed.query or parsed.fragment):
            raise HamokiError("HAMOKI_BASE_URL 必须是私人快传的 HTTPS 根地址")
        self.url=url
        self.host=parsed.hostname
        self.port=parsed.port or 443
        self.token=token if token is not None else os.environ.get("HAMOKI_AGENT_TOKEN","")
        if not TOKEN.fullmatch(self.token):
            raise HamokiError("请先在已配对设备管理中生成 AI 令牌并配置 HAMOKI_AGENT_TOKEN")

    def decode(self,body,status):
        try:
            payload=json.loads(body.decode("utf-8"))
        except (UnicodeError,ValueError):
            raise HamokiError("服务器响应无法解析") from None
        if not isinstance(payload,dict):
            raise HamokiError("服务器响应格式错误")
        if not 200<=status<300:
            raise HamokiError("HTTP %d: %s"%(status,payload.get("error","操作失败")))
        return payload

    def request(self,path,data=None):
        headers={"Authorization":"Bearer "+self.token,"X-Hamoki-Client":"1","Accept":"application/json"}
        if data is not None: headers["Content-Type"]="application/x-www-form-urlencoded"
        req=urllib.request.Request(self.url+path,data=data,headers=headers,
                                   method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req,timeout=45) as resp:
                return self.decode(resp.read(1024*1024),resp.status)
        except urllib.error.HTTPError as exc:
            return self.decode(exc.read(1024*1024),exc.code)
        except (OSError,urllib.error.URLError) as exc:
            raise HamokiError("网络异常，无法确认是否已发送；先读取最新内容再决定是否重试") from exc

    def send_text(self,text):
        if not isinstance(text,str) or not text.strip():
            raise HamokiError("请输入要发送的文字")
        length=len(text.strip().encode("utf-8"))
        if length>65536: raise HamokiError("私人文字最多64KiB")
        result=self.request("/api/private/send",urllib.parse.urlencode({"text":text}).encode())
        return {"ok":result.get("ok",False),"kind":"text","bytes":length}

    def get_latest(self):
        return self.request("/api/private/latest")

    def send_file(self,path_str):
        if not isinstance(path_str,str) or not path_str:
            raise HamokiError("需要用户指定的文件路径")
        path=Path(os.path.expandvars(os.path.expanduser(path_str))).absolute()
        try: info=path.lstat()
        except OSError as exc: raise HamokiError("文件不存在或无权读取") from exc
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise HamokiError("只能上传普通文件")
        if path.name.lower() in SENSITIVE or path.suffix.lower() in BLOCKED or path.name.startswith(".env."):
            raise HamokiError("此文件可能包含敏感凭证，不允许上传")
        if not 0<info.st_size<=MAX_SIZE:
            raise HamokiError("文件为空或超过5GiB")
        filename=path.name.replace('"','_').replace("\\","_").replace("\r","_").replace("\n","_")
        boundary="hamoki-"+secrets.token_hex(16)
        prefix=("--"+boundary+"\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\n\r\n"+
                "--"+boundary+"\r\nContent-Disposition: form-data; name=\"file\"; filename=\""+
                filename+"\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        suffix=("\r\n--"+boundary+"--\r\n").encode()
        conn=http.client.HTTPSConnection(self.host,self.port,timeout=120,context=ssl.create_default_context())
        try:
            conn.putrequest("POST","/api/private/send")
            conn.putheader("Authorization","Bearer "+self.token)
            conn.putheader("X-Hamoki-Client","1")
            conn.putheader("Content-Type","multipart/form-data; boundary="+boundary)
            conn.putheader("Content-Length",str(len(prefix)+info.st_size+len(suffix)))
            conn.endheaders()
            conn.send(prefix)
            with path.open("rb") as stream:
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk: break
                    conn.send(chunk)
            conn.send(suffix)
            response=conn.getresponse()
            result=self.decode(response.read(1024*1024),response.status)
            return {"ok":result.get("ok",False),"kind":"file","name":filename,"bytes":info.st_size}
        except HamokiError:
            raise
        except (OSError,http.client.HTTPException) as exc:
            raise HamokiError("传输异常，文件可能已经上传，请查看最新内容再决定是否重试") from exc
        finally: conn.close()

def dispatch(command):
    if not isinstance(command,dict): raise HamokiError("输入必须是 JSON 对象")
    action=command.get("skill_action","status")
    client=HamokiClient()
    if action=="send_text": return client.send_text(command.get("text",""))
    if action=="send_file": return client.send_file(command.get("file_path",""))
    if action=="get_latest": return client.get_latest()
    if action=="status":
        response=client.get_latest()
        return {"ok":True,"paired":True,"has_text":response.get("has_text",False),"has_file":response.get("has_file",False)}
    raise HamokiError("仅支持 send_text、send_file、get_latest、status")

if __name__=="__main__":
    try:
        print(json.dumps(dispatch(json.load(sys.stdin)),ensure_ascii=False))
    except (HamokiError,ValueError) as error:
        print(json.dumps({"ok":False,"error":str(error)},ensure_ascii=False))
        sys.exit(1)
