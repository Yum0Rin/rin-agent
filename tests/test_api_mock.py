import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rinlib  # noqa: E402
from runtime import rin  # noqa: E402


class MockHandler(BaseHTTPRequestHandler):
    calls = 0
    seen_tool_result = False

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))

        if MockHandler.calls == 0:
            body = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "note_add",
                                        "arguments": json.dumps(
                                            {
                                                "kind": "备忘",
                                                "content": "mock note",
                                                "visibility": "self",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        else:
            messages = payload.get("messages", [])
            MockHandler.seen_tool_result = any(
                item.get("role") == "tool" for item in messages
            )
            body = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "记下了。第 1 条。",
                        }
                    }
                ]
            }

        MockHandler.calls += 1
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # noqa: A002
        pass


class TestOpenAILoop(unittest.TestCase):
    def setUp(self):
        MockHandler.calls = 0
        MockHandler.seen_tool_result = False
        self.server = HTTPServer(("127.0.0.1", 0), MockHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self.cfg = rinlib.load_config(rinlib.example_config_path())
        self.cfg["runtime"]["base_url"] = (
            f"http://127.0.0.1:{self.server.server_port}/v1"
        )
        self.cfg["runtime"]["model"] = "mock"
        self.cfg["runtime"]["api_key"] = "test-key"
        self.cfg["runtime"]["use_tools"] = True

        self.tmp = tempfile.TemporaryDirectory()
        self.db = rin.init_db(Path(self.tmp.name) / "api.db")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.db.close()
        self.tmp.cleanup()

    def test_tool_call_then_reply(self):
        reply = rin.chat_turn(self.db, self.cfg, "owner", "帮我记一下 mock note")
        self.assertEqual(reply, "记下了。第 1 条。")
        self.assertTrue(MockHandler.seen_tool_result)
        rows = rin.search_notes(self.db, self.cfg, "owner", "mock")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "mock note")

        history = rin.history(self.db, "owner", 10)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[-1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
