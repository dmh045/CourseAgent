from pathlib import Path

import pytest

from tools.document_tool import read_document


def test_read_txt(tmp_path: Path) -> None:
    file_path = tmp_path / "course.txt"
    file_path.write_text("课程资料内容", encoding="utf-8")

    assert read_document(str(file_path)) == "课程资料内容"


def test_read_docx(tmp_path: Path) -> None:
    pytest.importorskip("docx")
    from docx import Document

    file_path = tmp_path / "course.docx"
    doc = Document()
    doc.add_paragraph("Word 课程资料")
    doc.save(file_path)

    assert "Word 课程资料" in read_document(str(file_path))


def test_read_pdf(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")

    file_path = tmp_path / "course.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "PDF course content")
    doc.save(file_path)
    doc.close()

    assert "PDF course content" in read_document(str(file_path))


def test_unsupported_format(tmp_path: Path) -> None:
    file_path = tmp_path / "course.xlsx"
    file_path.write_text("bad", encoding="utf-8")

    with pytest.raises(ValueError):
        read_document(str(file_path))
