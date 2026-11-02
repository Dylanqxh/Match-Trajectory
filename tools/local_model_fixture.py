"""Loopback-only test fixture. Not an AI model and never used by the app by default."""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 500000:
            self.send_error(413)
            return
        payload = json.loads(self.rfile.read(size))
        system = payload["messages"][0]["content"] if len(payload["messages"]) > 1 else ""
        context = json.loads(payload["messages"][1]["content"]) if system else {}
        if not system:
            output = {"ok": True}
        elif "当前阶段：plan" in system:
            if "补问" in context["evidence"][0]["text"] and context.get("question_budget"):
                output = {"decision": "ask", "selected_fact_ids": ["e1"], "questions": [{"id": "q1", "text": "你本人已经交付了什么？"}]}
            else:
                output = {"decision": "draft", "selected_fact_ids": ["e1"], "focus": ["保留实际动作"]}
        elif "当前阶段：review" in system:
            output = {"verdict": "pass", "issues": [], "strengths": ["本地协议测试，非真实模型评价"]}
        else:
            output = {"sections": [{"id": "projects", "title": "项目经历", "items": [
                {"id": "item1", "text": context["evidence"][0]["text"], "fact_ids": ["e1"]},
            ]}]}
        time.sleep(0.05)
        data = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output, ensure_ascii=False)}}],
                           "usage": {"total_tokens": 10}}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()
