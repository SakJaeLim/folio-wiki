"""WeKnora v0.9.0 API. Each immutable folder snapshot owns one draft KB."""

import json
import os
import secrets
import threading
from pathlib import Path
from urllib import error, parse, request

from .store import pack


class Engine:
    def __init__(self, store, base, directory):
        url = parse.urlsplit(base)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.query
            or url.fragment
            or url.username
        ):
            raise ValueError("WeKnora 서버 주소를 확인해 주세요.")
        if url.scheme == "http" and url.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("외부 WeKnora 서버 연결에는 HTTPS가 필요합니다.")
        self.base = base.rstrip("/") + "/api/v1"
        self.store = store
        self.token = None
        self.tenant = None
        self.wake = threading.Event()
        self.closed = threading.Event()
        self.account = Path(directory) / "engine-account.json"
        if not self.account.exists():
            self.account.write_text(
                json.dumps(
                    {
                        "email": f"folio-{secrets.token_hex(6)}@example.org",
                        "password": "Fw!" + secrets.token_hex(12),
                    }
                ),
                encoding="utf-8",
            )
            self.account.chmod(0o600)
        self.identity = json.loads(self.account.read_text(encoding="utf-8"))

    def call(self, path, method="GET", body=None):
        headers = {"Content-Type": "application/json", "Accept-Language": "ko-KR"}
        if self.token:
            headers.update(
                Authorization="Bearer " + self.token,
                **{"X-Tenant-ID": str(self.tenant)},
            )
        req = request.Request(
            self.base + path,
            method=method,
            headers=headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except error.HTTPError as exc:
            if exc.code == 401:
                self.token = None
            raise

    def authenticate(self):
        account = {k: self.identity[k] for k in ("email", "password")}
        try:
            login = self.call("/auth/login", "POST", account)
        except error.HTTPError as exc:
            if exc.code not in (400, 401, 403, 404):
                raise
            self.call("/auth/register", "POST", {**account, "username": "Folio Wiki"})
            login = self.call("/auth/login", "POST", account)
        data = login.get("data", login)
        self.token = data["token"]
        self.tenant = (data.get("active_tenant") or data.get("tenant") or {})["id"]

    def create_kb(self, snap):
        name = "Folio " + self.identity["email"].split("@")[0] + " " + snap["id"]
        existing = self.call("/knowledge-bases").get("data", [])
        if isinstance(existing, dict):
            existing = existing.get("items", existing.get("knowledge_bases", []))
        for kb in existing or []:
            if kb["name"] == name:
                return kb["id"]
        chat = os.getenv("FOLIO_CHAT_MODEL_ID", "builtin-lab-chat")
        params = {
            "name": name,
            "description": "공개 폴더 버전별 위키 초안",
            "type": "document",
            "embedding_model_id": os.getenv(
                "FOLIO_EMBED_MODEL_ID", "builtin-lab-embedding"
            ),
            "summary_model_id": chat,
            "indexing_strategy": {
                "vector_enabled": True,
                "keyword_enabled": True,
                "wiki_enabled": True,
                "graph_enabled": False,
            },
            "chunking_config": {"chunk_size": 800, "chunk_overlap": 60},
            "wiki_config": {
                "synthesis_model_id": chat,
                "max_pages_per_ingest": 2,
                "extraction_granularity": "focused",
                "ingest_batch_size": 1,
                "ingest_map_parallel": 1,
                "ingest_reduce_parallel": 1,
                "ingest_max_inflight": 1,
                "extraction_instructions": "공개 폴더에서 업무 주제를 추출하세요.",
                "content_instructions": "한국어로 짧게 작성하세요. 파일별 출처와 수치를 유지하세요. 상이한 기준을 하나로 정하지 마세요.",
            },
        }
        return self.call("/knowledge-bases", "POST", params)["data"]["id"]

    def tick(self, snap):
        refs = json.loads(snap["files"])
        if not refs:
            self.store.engine_update(
                snap["id"],
                engine="empty",
                pages="[]",
                detail="공개 폴더에 Markdown 문서를 넣어 주세요.",
            )
            return
        if not self.token:
            self.authenticate()
        kb = snap["kb"] or self.create_kb(snap)
        if not snap["kb"]:
            self.store.engine_update(snap["id"], kb=kb)
        if not snap["remote_doc"]:
            title = "공개 폴더 " + snap["id"][:12]
            docs = self.call(
                f"/knowledge-bases/{kb}/knowledge?page=1&page_size=100"
            ).get("data", [])
            remote = next((d for d in docs if d["title"] == title), None)
            if not remote:
                parts = [
                    f"파일: {p}\n\n" + self.store.source(p, v)["body"]
                    for p, v in refs.items()
                ]
                remote = self.call(
                    f"/knowledge-bases/{kb}/knowledge/manual",
                    "POST",
                    {
                        "title": title,
                        "status": "publish",
                        "content": "\n\n---\n\n".join(parts),
                    },
                )["data"]
            self.store.engine_update(snap["id"], remote_doc=remote["id"])
        pages = self.call(f"/knowledgebase/{kb}/wiki/pages?page_size=100").get(
            "pages", []
        )
        stats = self.call(f"/knowledgebase/{kb}/wiki/stats")
        docs = self.call(f"/knowledge-bases/{kb}/knowledge?page=1&page_size=100").get(
            "data", []
        )
        failed = next((d for d in docs if d.get("parse_status") == "failed"), None)
        if failed:
            raise RuntimeError(
                "문서를 처리하지 못했습니다. WeKnora의 문서 처리 기록을 확인해 주세요."
            )
        result = [
            {
                k: p.get(k)
                for k in (
                    "slug",
                    "title",
                    "page_type",
                    "content",
                    "version",
                    "source_refs",
                )
            }
            for p in pages
        ]
        ready = (
            any(p.get("page_type") != "index" for p in pages)
            and not stats.get("pending_tasks")
            and not stats.get("is_active")
            and docs
            and all(d.get("parse_status") == "completed" for d in docs)
        )
        self.store.engine_update(
            snap["id"],
            pages=pack(result),
            engine="ready" if ready else "building",
            detail=""
            if ready
            else "WeKnora가 공개 자료로 위키 초안을 작성하고 있습니다.",
        )

    def run(self):
        while not self.closed.is_set():
            self.wake.clear()
            snap = self.store.snapshot()
            if snap and snap["engine"] != "empty":
                try:
                    self.tick(snap)
                except (OSError, KeyError, ValueError, TypeError, RuntimeError) as exc:
                    message = f"WeKnora 연결 또는 처리 대기 중 ({type(exc).__name__}"
                    if isinstance(exc, error.HTTPError):
                        message += f" {exc.code}"
                    self.store.engine_update(
                        snap["id"], engine="waiting", detail=message + ")."
                    )
            self.wake.wait(60 if snap and snap["engine"] == "ready" else 12)
