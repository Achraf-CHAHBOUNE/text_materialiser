"""docx writer must survive OCR text with XML-illegal control/NULL characters."""
from docx import Document

from anonymizer.documents.docx_writer import _xml_safe, write_docx


def test_xml_safe_strips_control_chars_keeps_content():
    dirty = "محكمة\x00 النقض\x07 الغرفة\x1f المدنية\tمع\nسطر"
    clean = _xml_safe(dirty)
    assert "\x00" not in clean and "\x07" not in clean and "\x1f" not in clean
    assert "محكمة" in clean and "\t" in clean and "\n" in clean  # tab/newline preserved


def test_write_docx_with_control_chars_does_not_crash(tmp_path):
    out = tmp_path / "d.docx"
    write_docx(["نص\x00 يحتوي\x0c على\x08 محارف تحكم"], out, title="عنوان\x00 المحكمة")
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "\x00" not in text and "يحتوي" in text
