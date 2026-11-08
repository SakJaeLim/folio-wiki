"""Launch the local Folio Wiki review desk."""

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from folio import demo
from folio.documents import digest
from folio.integrations import advice, outline
from folio.store import Conflict, Store
from folio.weknora import Engine

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--folder", type=Path)
    mode.add_argument(
        "--demo",
        action="store_true",
        help="Try the review desk with a local workshop example",
    )
    mode.add_argument(
        "--revise-demo",
        action="store_true",
        help="Change the demo notice from 14 to 10 days",
    )
    parser.add_argument("--state", type=Path)
    parser.add_argument("--port", type=int, default=8848)
    parser.add_argument("--weknora-url", default="http://127.0.0.1:8794")
    parser.add_argument(
        "--enable-jev",
        action="store_true",
        help="Allow explicit public-excerpt calls to TypeSafe",
    )
    args = parser.parse_args()
    if args.revise_demo:
        try:
            demo.revise(ROOT)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print("Demo notice now uses the 10-day deadline.")
        return
    folder = (
        demo.prepare(ROOT)
        if args.demo
        else (args.folder or ROOT / "examples/public-handbook").resolve(strict=True)
    )
    if args.state is None:
        args.state = (
            ROOT / ".state" / "folders" / digest(os.path.normcase(str(folder)))[:24]
        )
    store = Store(args.state)
    lock = threading.Lock()

    def sync():
        with lock:
            return store.sync(folder)

    sync()
    engine = None if args.demo else Engine(store, args.weknora_url, args.state)
    stopped = engine.closed if engine else threading.Event()
    if engine:
        threading.Thread(target=engine.run, daemon=True).start()

    def notify_engine():
        if engine:
            engine.wake.set()

    scan_status = {"sync_error": ""}

    def watch():
        while not stopped.wait(4):
            before = store.snapshot()
            try:
                after = sync()
                scan_status["sync_error"] = ""
                if not before or before["id"] != after:
                    notify_engine()
            except (ValueError, OSError) as exc:
                scan_status["sync_error"] = "폴더를 읽지 못했습니다. " + str(exc)

    threading.Thread(target=watch, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, kind="application/json; charset=utf-8"):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def dispatch(self, post=False):
            if self.headers.get("Host") not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                return self.send(403, {"error": "로컬 주소로 접속해 주세요."})
            url = urlsplit(self.path)
            if post:
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + self.headers["Host"]:
                    return self.send(403, {"error": "허용되지 않은 요청입니다."})
                if self.headers.get_content_type() != "application/json":
                    return self.send(415, {})
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size < 32768:
                    return self.send(400, {})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("JSON 객체가 필요합니다.")
                if url.path == "/api/sync":
                    sync()
                    notify_engine()
                elif url.path == "/api/decide":
                    # Read disk again before committing an old screen's choice.
                    with lock:
                        store.sync(folder)
                        store.decide(
                            body["topic"],
                            body["generation"],
                            body["selection"],
                            body["actor"],
                            body["note"],
                            body.get("unit"),
                            body.get("scope", ""),
                            body.get("audience", ""),
                        )
                    notify_engine()
                elif url.path == "/api/advice":
                    if not args.enable_jev:
                        return self.send(
                            403, {"error": "Jev 연결을 켠 뒤 다시 시도해 주세요."}
                        )
                    sync()
                    topic = next(
                        (
                            x
                            for x in store.view()["topics"]
                            if x["name"] == body["topic"]
                        ),
                        None,
                    )
                    if not topic or topic["generation"] != body["generation"]:
                        raise Conflict("원문이 바뀌었습니다.")
                    ids = body["ids"]
                    if not isinstance(ids, list) or len(set(ids)) != 2:
                        raise ValueError("서로 다른 원문 두 개가 필요합니다.")
                    items = [x for x in topic["candidates"] if x["id"] in ids]
                    return self.send(200, advice(items))
                else:
                    return self.send(404, {})
                return self.send(200, {"ok": True})
            if url.path == "/api/view":
                return self.send(
                    200,
                    {
                        **store.view(),
                        **scan_status,
                        "demo": args.demo,
                        "folder": folder.name,
                        "jev": args.enable_jev,
                    },
                )
            if url.path == "/api/source":
                q = parse_qs(url.query)
                doc = store.source(q["path"][0], q["version"][0])
                return self.send(
                    200,
                    {
                        **doc,
                        "outline": outline(
                            doc["path"], doc["version"], doc["body"], args.state
                        ),
                    },
                )
            assets = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if url.path in assets:
                name, kind = assets[url.path]
                return self.send(
                    200, (ROOT / "web" / name).read_bytes(), kind + "; charset=utf-8"
                )
            self.send(404, {})

        def handle_request(self, post=False):
            try:
                self.dispatch(post)
            except Conflict as exc:
                self.send(409, {"error": str(exc)})
            except (ValueError, KeyError, UnicodeError, OSError) as exc:
                self.send(400, {"error": str(exc)})

        do_GET = handle_request

        def do_POST(self):
            self.handle_request(True)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Folio Wiki http://127.0.0.1:{http.server_port}/   {folder}", flush=True)
    try:
        http.serve_forever()
    finally:
        stopped.set()
        notify_engine()
        http.server_close()


if __name__ == "__main__":
    main()
