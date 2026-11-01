"""A small real PDF for tests: one page of plain text per string."""


def make_pdf(pages: list[str]) -> bytes:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]  # the page tree is filled in below
    kids = []
    for text in pages:
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 11 Tf 50 750 Td ({safe}) Tj ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {len(objects)} 0 R /Resources << /Font << /F1 FONT 0 R >> >> >>"
        )
        kids.append(f"{len(objects)} 0 R")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font = len(objects)
    objects = [o.replace("FONT", str(font)) for o in objects]
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


def with_title(pdf: bytes, title: str) -> bytes:
    """The same PDF, with a title in its metadata as a publisher would set it."""
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    writer.add_metadata({"/Title": title})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
