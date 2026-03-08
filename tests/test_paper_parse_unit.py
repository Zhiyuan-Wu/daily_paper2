from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

import pytest

from service.parse.paper_parser import PaperParser


def _create_minimal_papers_table(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE papers (
                id TEXT PRIMARY KEY,
                local_pdf_path TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _DummyImage:
    def __init__(self, label: str) -> None:
        self.label = label

    def save(self, buffer, format: str) -> None:  # noqa: A003
        buffer.write(f"image:{self.label}:{format}".encode("utf-8"))


def test_parse_images_accepts_path_and_base64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "papers.db"
    _create_minimal_papers_table(db_path)
    parser = PaperParser(db_path=db_path, parsed_dir=tmp_path / "parsed")

    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"image-from-path")
    image_b64 = base64.b64encode(b"image-from-b64").decode("utf-8")

    def fake_post(url: str, json: dict, timeout: int):  # noqa: ANN001
        images = (((json.get("messages") or [{}])[0]).get("images") or [])
        return _FakeResponse({"message": {"content": f"ok:{len(images[0])}:{timeout}"}})

    monkeypatch.setattr("service.parse.paper_parser.requests.post", fake_post)
    result = parser.parse_images([str(image_path), image_b64])
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(item.startswith("ok:") for item in result)


def test_parse_pdfs_reuses_image_parser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "papers.db"
    _create_minimal_papers_table(db_path)
    parser = PaperParser(db_path=db_path, parsed_dir=tmp_path / "parsed")

    monkeypatch.setattr(parser, "_convert_pdf_to_images", lambda _: [_DummyImage("1"), _DummyImage("2")])
    monkeypatch.setattr(parser, "_ocr_with_ollama", lambda image_base64: f"text:{len(image_base64)}")

    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%demo\n")

    text = parser.parse_pdfs(pdf_path)
    assert isinstance(text, str)
    assert "## Page 1" in text
    assert "## Page 2" in text
    assert "text:" in text


def test_parse_paper_updates_sqlite_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "papers.db"
    _create_minimal_papers_table(db_path)
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%demo\n")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO papers (id, local_pdf_path) VALUES (?, ?)", ("demo:1", str(pdf_path)))
        conn.commit()
    finally:
        conn.close()

    parser = PaperParser(
        db_path=db_path,
        parsed_dir=tmp_path / "parsed",
        ollama_model="unit-test-model",
    )
    monkeypatch.setattr(parser, "_parse_one_pdf", lambda _: ("# Parsed\n\nhello\n", 1))

    out_path = parser.parse_paper("demo:1")
    assert Path(out_path).exists()
    assert "hello" in Path(out_path).read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        parse_row = conn.execute(
            "SELECT status, local_text_path, page_count, ocr_model FROM paper_parses WHERE paper_id = ?",
            ("demo:1",),
        ).fetchone()
        assert parse_row is not None
        assert parse_row[0] == "success"
        assert parse_row[1] == out_path
        assert parse_row[2] == 1
        assert parse_row[3] == "unit-test-model"

        paper_row = conn.execute("SELECT local_text_path FROM papers WHERE id = ?", ("demo:1",)).fetchone()
        assert paper_row is not None
        assert paper_row[0] == out_path
    finally:
        conn.close()
