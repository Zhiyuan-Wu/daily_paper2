from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from models.paper import PaperMetadata
from service.fetch.repository import PaperRepository
from service.parse.paper_parser import PaperParser

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PDF = ROOT / "data/papers/arxiv_2603.05500.pdf"


def _pdf2image_available() -> bool:
    if shutil.which("pdftoppm") is None:
        return False
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return False
    try:
        images = convert_from_path(str(SAMPLE_PDF), dpi=50, first_page=1, last_page=1)
    except Exception:  # noqa: BLE001
        return False
    return bool(images)


class _FakeOllamaHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        images = ((payload.get("messages") or [{}])[0]).get("images") or []
        one_size = len(images[0]) if images else 0
        body = {"message": {"content": f"OCR_TEXT image_count={len(images)} image_b64_len={one_size}"}}

        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None


@pytest.fixture
def fake_ollama_endpoint() -> str:
    server = HTTPServer(("127.0.0.1", 0), _FakeOllamaHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/api/chat"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _prepare_db_with_pdf(db_path: Path, copied_pdf: Path, paper_id: str) -> None:
    repo = PaperRepository(db_path)
    paper = PaperMetadata(
        id=paper_id,
        source="arxiv",
        source_id=paper_id.split(":", 1)[1],
        title="E2E Parse Target",
        authors=["Tester"],
        abstract="for parser e2e test",
        online_url="https://example.org",
        local_pdf_path=str(copied_pdf),
    )
    repo.upsert_papers([paper])


@pytest.mark.e2e
def test_e2e_parse_paper_and_db_state(tmp_path: Path, fake_ollama_endpoint: str) -> None:
    if not _pdf2image_available():
        pytest.skip("pdf2image/poppler not available for parser e2e")
    if not SAMPLE_PDF.exists():
        pytest.skip(f"sample pdf missing: {SAMPLE_PDF}")

    db_path = tmp_path / "papers.db"
    parsed_dir = tmp_path / "parsed"
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    copied_pdf = papers_dir / "arxiv_2603.05500.pdf"
    copied_pdf.write_bytes(SAMPLE_PDF.read_bytes())

    paper_id = "arxiv:2603.05500"
    _prepare_db_with_pdf(db_path, copied_pdf, paper_id)

    parser = PaperParser(
        db_path=db_path,
        parsed_dir=parsed_dir,
        ollama_endpoint=fake_ollama_endpoint,
        ollama_model="fake-ocr",
        ocr_timeout=30,
        pdf_dpi=120,
    )
    local_text_path = parser.parse_paper(paper_id)

    output = Path(local_text_path)
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "## Page 1" in content
    assert "OCR_TEXT" in content

    conn = sqlite3.connect(db_path)
    try:
        parse_row = conn.execute(
            "SELECT status, local_text_path, page_count, ocr_model FROM paper_parses WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        assert parse_row is not None
        assert parse_row[0] == "success"
        assert parse_row[1] == str(output)
        assert parse_row[2] >= 1
        assert parse_row[3] == "fake-ocr"

        paper_row = conn.execute(
            "SELECT local_text_path FROM papers WHERE id = ?",
            (paper_id,),
        ).fetchone()
        assert paper_row is not None
        assert paper_row[0] == str(output)
    finally:
        conn.close()


@pytest.mark.e2e
def test_e2e_cli_parse_paper(tmp_path: Path, fake_ollama_endpoint: str) -> None:
    if not _pdf2image_available():
        pytest.skip("pdf2image/poppler not available for parser e2e")
    if not SAMPLE_PDF.exists():
        pytest.skip(f"sample pdf missing: {SAMPLE_PDF}")

    db_path = tmp_path / "papers.db"
    parsed_dir = tmp_path / "parsed"
    papers_dir = tmp_path / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    copied_pdf = papers_dir / "arxiv_2603.05500.pdf"
    copied_pdf.write_bytes(SAMPLE_PDF.read_bytes())

    paper_id = "arxiv:2603.05500"
    _prepare_db_with_pdf(db_path, copied_pdf, paper_id)

    cmd = [
        sys.executable,
        str(ROOT / "scripts/paper_parse_cli.py"),
        "--db-path",
        str(db_path),
        "--parsed-dir",
        str(parsed_dir),
        "--endpoint",
        fake_ollama_endpoint,
        "--model",
        "fake-ocr-cli",
        "--timeout",
        "30",
        "--dpi",
        "120",
        "paper",
        paper_id,
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["paper_id"] == paper_id
    assert payload["status"] == "success"
    assert Path(payload["local_text_path"]).exists()
