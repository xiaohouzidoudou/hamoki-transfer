#!/usr/bin/env python3
"""Small stdio MCP JSON-RPC server for Hamoki. Python 3.10+, no extra packages."""
import json
import sys
from run import HamokiClient, HamokiError

TOOLS=[
 {"name":"send_text","description":"Send explicit text to the paired Hamoki private room, replacing its current latest content.",
  "inputSchema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False}},
 {"name":"send_file","description":"Upload one specifically authorized local file from this device to the paired Hamoki room.",
  "inputSchema":{"type":"object","properties":{"file_path":{"type":"string"}},"required":["file_path"],"additionalProperties":False}},
 {"name":"get_latest","description":"Read the private room's latest text and file metadata.",
  "inputSchema":{"type":"object","properties":{},"additionalProperties":False}}
]

def answer(req):
    method=req.get("method")
    if method=="initialize":
        version=req.get("params",{}).get("protocolVersion","2025-03-26")
        supported={"2024-11-05","2025-03-26","2025-06-18","2025-11-25"}
        return {"protocolVersion":version if version in supported else "2025-03-26",
                "capabilities":{"tools":{"listChanged":False}},
                "serverInfo":{"name":"hamoki-private-ai","version":"1.0.0"}}
    if method=="ping": return {}
    if method=="tools/list": return {"tools":TOOLS}
    if method=="tools/call":
        params=req.get("params") or {}
        arguments=params.get("arguments") or {}
        name=params.get("name")
        try:
            if name=="send_text":
                result=HamokiClient().send_text(arguments.get("text",""))
            elif name=="send_file":
                result=HamokiClient().send_file(arguments.get("file_path",""))
            elif name=="get_latest":
                result=HamokiClient().get_latest()
            else:
                raise HamokiError("工具不存在")
            return {"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False)}],"isError":False}
        except (HamokiError,ValueError,TypeError) as err:
            return {"content":[{"type":"text","text":str(err)}],"isError":True}
    return None

def main():
    for raw in sys.stdin:
        try:
            req=json.loads(raw)
            if not isinstance(req,dict) or "id" not in req: continue
            data=answer(req)
            packet={"jsonrpc":"2.0","id":req["id"]}
            if data is None:
                packet["error"]={"code":-32601,"message":"Method not found"}
            else:
                packet["result"]=data
            sys.stdout.write(json.dumps(packet,ensure_ascii=False,separators=(',',':'))+"\n")
            sys.stdout.flush()
        except Exception as err:
            print("Hamoki MCP protocol error:",type(err).__name__,file=sys.stderr)

if __name__=="__main__": main()
