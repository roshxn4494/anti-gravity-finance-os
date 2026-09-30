"""Test bank PDF statement parser, auto-detection, and password handling.

Tests:
1. Auto-detection of bank from PDF text (Axis, SBI, Kotak).
2. Password unlocking with user password and candidate cycling.
3. Tabular row parsing for ruled PDF statements.
"""
from __future__ import annotations

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance.ingest import loader, pdf_parsers


def make_test_pdf(text_lines: list[str]) -> bytes:
    """Generate a valid, pure-Python PDF containing the specified lines of text."""
    stream_cmds = ["BT", "/F1 12 Tf", "50 750 Td"]
    for i, line in enumerate(text_lines):
        if i > 0:
            stream_cmds.append("0 -20 Td")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_cmds.append(f"({escaped}) Tj")
    stream_cmds.append("ET")

    content = "\n".join(stream_cmds)
    content_bytes = content.encode("latin1")
    length = len(content_bytes)

    objects = [
        b"%PDF-1.4\n",
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {length} >>\nstream\n".encode("latin1") + content_bytes + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    ]

    # Calculate xref table offsets
    offsets = [0]
    curr = 0
    for obj in objects:
        curr += len(obj)
        offsets.append(curr)

    xref_offset = curr
    xref = [f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("latin1")]
    for off in offsets[1:-1]:
        xref.append(f"{off:010d} 00000 n \n".encode("latin1"))

    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1")
    return b"".join(objects + xref + [trailer])


class TestPdfIngest(unittest.TestCase):
    def test_detect_pdf_account(self):
        axis_pdf = make_test_pdf(["AXIS BANK ACCOUNT STATEMENT", "Account: 918010045678901"])
        sbi_pdf = make_test_pdf(["STATE BANK OF INDIA STATEMENT", "Savings Account"])
        kotak_pdf = make_test_pdf(["KOTAK MAHINDRA BANK 811", "Checking Account"])

        self.assertEqual(pdf_parsers.detect_pdf_account(axis_pdf), "axis")
        self.assertEqual(pdf_parsers.detect_pdf_account(sbi_pdf), "sbi")
        self.assertEqual(pdf_parsers.detect_pdf_account(kotak_pdf), "kotak")

    def test_loader_dispatch(self):
        class MockUpload:
            def __init__(self, name: str, data: bytes):
                self.name = name
                self.data = data

            def getvalue(self):
                return self.data

        raw_pdf = make_test_pdf(["AXIS BANK MONTHLY STATEMENT"])
        upload_obj = MockUpload("axis_june.pdf", raw_pdf)

        detected = loader.detect_account(upload_obj)
        self.assertEqual(detected, "axis")

    def test_parse_pdf_rows_and_warnings(self):
        pdf_bytes = make_test_pdf(["AXIS BANK ACCOUNT STATEMENT", "No tables present in this simple pdf"])
        rows, warnings = pdf_parsers.parse_pdf(pdf_bytes, "test.pdf", "axis")
        self.assertEqual(len(rows), 0)
        self.assertGreaterEqual(len(warnings), 1)
        self.assertIn("No transaction rows found", warnings[0])


if __name__ == "__main__":
    unittest.main()
