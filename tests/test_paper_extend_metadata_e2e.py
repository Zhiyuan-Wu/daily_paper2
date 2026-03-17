from __future__ import annotations

import json
import importlib.util
import shutil
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from service.extend_metadata import PaperExtendMetadataService
from service.extend_metadata.openai_client import OpenAIExtendMetadataClient
from service.fetch.paper_fetch import PaperFetch
from service.parse.paper_parser import PaperParser

ROOT = Path(__file__).resolve().parents[1]
OPENAI_AVAILABLE = importlib.util.find_spec("openai") is not None


def _pdf2image_available() -> bool:
    if shutil.which("pdftoppm") is None:
        return False
    try:
        from pdf2image import convert_from_path  # noqa: F401
    except ImportError:
        return False
    return True


class _FakeOcrHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        body = {
            "message": {
                "content": (
                    "Title: Demo Paper\n"
                    "Affiliations: OpenAI; Tsinghua University\n"
                    "Keywords: llm, agents, reasoning\n"
                    "Code: https://github.com/example/project\n"
                )
            }
        }
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        body = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 1,
            "model": "fake-chat",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "abstract_cn": "这是一段中文摘要翻译。",
                                "affliations": ["OpenAI", "Tsinghua University"],
                                "keywords": ["llm", "agents", "reasoning"],
                                "github_repo": "https://github.com/example/project",
                            },
                            ensure_ascii=False,
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None


@pytest.fixture
def fake_ocr_endpoint() -> str:
    server = HTTPServer(("127.0.0.1", 0), _FakeOcrHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/api/chat"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def fake_openai_base_url() -> str:
    server = HTTPServer(("127.0.0.1", 0), _FakeOpenAIHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.mark.e2e
@pytest.mark.skipif(not OPENAI_AVAILABLE, reason="openai package not installed")
def test_e2e_extend_metadata_extract_and_db_state(
    tmp_path: Path,
    fake_ocr_endpoint: str,
    fake_openai_base_url: str,
) -> None:
    if not _pdf2image_available():
        pytest.skip("pdf2image/poppler not available for extend metadata e2e")

    db_path = tmp_path / "papers.db"
    papers_dir = tmp_path / "papers"
    parsed_dir = tmp_path / "parsed"

    fetch = PaperFetch(
        db_path=db_path,
        papers_dir=papers_dir,
        max_downloaded_papers=10,
    )
    papers = fetch.search_online(
        source="arxiv",
        start_date="2026-03-01",
        end_date="2026-03-08",
        keywords=["llm"],
        limit=1,
        category="cs.AI",
    )
    if not papers:
        pytest.skip("arXiv returned no papers for extend metadata e2e query")

    parser = PaperParser(
        db_path=db_path,
        parsed_dir=parsed_dir,
        ollama_endpoint=fake_ocr_endpoint,
        ollama_model="fake-ocr",
        ocr_timeout=30,
        pdf_dpi=120,
    )
    llm_client = OpenAIExtendMetadataClient(
        base_url=fake_openai_base_url,
        api_key="test-key",
        model="fake-chat",
        timeout_seconds=30,
    )
    service = PaperExtendMetadataService(
        db_path=db_path,
        fetch_service=fetch,
        parser=parser,
        llm_client=llm_client,
    )

    payload = service.get_extended_metadata(papers[0].id)
    assert payload["paper_id"] == papers[0].id
    assert payload["affliations"] == ["OpenAI", "Tsinghua University"]
    assert payload["keywords"] == ["llm", "agents", "reasoning"]
    assert payload["github_repo"] == "https://github.com/example/project"

    conn = sqlite3.connect(db_path)
    try:
        metadata_row = conn.execute(
            "SELECT abstract_cn, affliations, keywords, github_repo FROM extend_metadata WHERE paper_id = ?",
            (papers[0].id,),
        ).fetchone()
        assert metadata_row is not None
        assert metadata_row[0] == "这是一段中文摘要翻译。"
        assert json.loads(metadata_row[1]) == ["OpenAI", "Tsinghua University"]
        assert json.loads(metadata_row[2]) == ["llm", "agents", "reasoning"]
        assert metadata_row[3] == "https://github.com/example/project"

        paper_row = conn.execute(
            "SELECT local_pdf_path FROM papers WHERE id = ?",
            (papers[0].id,),
        ).fetchone()
        assert paper_row is not None
        assert paper_row[0]
        assert Path(paper_row[0]).exists()
        assert Path(paper_row[0]).stat().st_size > 1024
    finally:
        conn.close()


@pytest.mark.e2e
@pytest.mark.skipif(not OPENAI_AVAILABLE, reason="openai package not installed")
def test_e2e_cli_extend_metadata(
    tmp_path: Path,
    fake_ocr_endpoint: str,
    fake_openai_base_url: str,
) -> None:
    if not _pdf2image_available():
        pytest.skip("pdf2image/poppler not available for extend metadata e2e")

    db_path = tmp_path / "papers.db"
    papers_dir = tmp_path / "papers"
    fetch = PaperFetch(
        db_path=db_path,
        papers_dir=papers_dir,
        max_downloaded_papers=10,
    )

    papers = fetch.search_online(
        source="arxiv",
        start_date="2026-03-01",
        end_date="2026-03-08",
        keywords=["llm"],
        limit=1,
        category="cs.AI",
    )
    if not papers:
        pytest.skip("arXiv returned no papers for extend metadata cli e2e query")

    cmd = [
        sys.executable,
        str(ROOT / "scripts/paper_extend_metadata_cli.py"),
        "--db-path",
        str(db_path),
        "--papers-dir",
        str(papers_dir),
        "--parsed-dir",
        str(tmp_path / "parsed"),
        "--ocr-endpoint",
        fake_ocr_endpoint,
        "--ocr-model",
        "fake-ocr-cli",
        "--ocr-timeout",
        "30",
        "--dpi",
        "120",
        "--base-url",
        fake_openai_base_url,
        "--api-key",
        "test-key",
        "--model",
        "fake-chat-cli",
        "--llm-timeout",
        "30",
        "paper",
        papers[0].id,
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["paper_id"] == papers[0].id
    assert payload["github_repo"] == "https://github.com/example/project"
