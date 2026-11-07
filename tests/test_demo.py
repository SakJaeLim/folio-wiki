"""Exercise the commands a new user copies from the README."""

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]


class DemoCommands(unittest.TestCase):
    def test_fresh_checkout_preserves_adopted_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / "folio-wiki"
            checkout.mkdir()
            shutil.copy2(ROOT / "run.py", checkout)
            for name in ("folio", "web", "examples"):
                shutil.copytree(
                    ROOT / name,
                    checkout / name,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            cmd = [sys.executable, "-S", "run.py"]
            server = subprocess.Popen(
                [*cmd, "--demo", "--port", str(port)],
                cwd=checkout,
                stdout=subprocess.DEVNULL,
            )

            def api(path, payload=None):
                body = json.dumps(payload).encode() if payload is not None else None
                req = request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with request.urlopen(req, timeout=3) as response:
                    return json.load(response)

            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        initial = api("/api/view")
                        break
                    except OSError:
                        if server.poll() is not None or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.1)
                self.assertTrue(initial["demo"])
                topic = initial["topics"][0]
                chosen = next(c for c in topic["candidates"] if "14일" in c["quote"])
                api(
                    "/api/decide",
                    {
                        "topic": topic["name"],
                        "generation": topic["generation"],
                        "selection": chosen["id"],
                        "actor": "운영팀",
                        "note": "이번 공지 적용",
                    },
                )
                self.assertEqual(api("/api/view")["topics"][0]["status"], "adopted")
                subprocess.run(
                    [*cmd, "--revise-demo"],
                    cwd=checkout,
                    check=True,
                    capture_output=True,
                )
                deadline = time.monotonic() + 12
                while (current := api("/api/view"))["topics"][0][
                    "status"
                ] != "review_again":
                    if time.monotonic() >= deadline:
                        self.fail("The folder watcher did not reopen the decision.")
                    time.sleep(0.25)
                self.assertTrue(
                    any(
                        "10일" in c["quote"] for c in current["topics"][0]["candidates"]
                    )
                )
                query = parse.urlencode(
                    {"path": chosen["path"], "version": chosen["version"]}
                )
                self.assertIn("14일", api("/api/source?" + query)["body"])
                self.assertFalse(
                    list((checkout / ".state").rglob("engine-account.json"))
                )
                original = checkout / "examples/public-handbook" / chosen["path"]
                self.assertIn("14일", original.read_text(encoding="utf-8"))
                copied = checkout / ".state/demo/공개 워크숍" / chosen["path"]
                copied.write_text("A personal edit.", encoding="utf-8")
                refused = subprocess.run(
                    [*cmd, "--revise-demo"],
                    cwd=checkout,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(refused.returncode, 0)
                self.assertEqual(copied.read_text(encoding="utf-8"), "A personal edit.")
            finally:
                server.terminate()
                server.wait(timeout=10)
