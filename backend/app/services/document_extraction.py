"""Safe, format-specific text extraction for uploaded documents."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class DocumentExtractionError(ValueError):
    """Raised for malformed or unsupported document content."""


@dataclass(frozen=True)
class ExtractedPage:
    content: str
    page_number: int | None


class DocumentExtractor:
    """Extracts UTF-8 text and PDF page text without executing document content."""

    async def extract(self, *, content: bytes, content_type: str) -> list[ExtractedPage]:
        if content_type in {"text/plain", "text/markdown"}:
            return [ExtractedPage(content=self._decode_text(content), page_number=None)]
        if content_type == "application/pdf":
            return self._extract_pdf(content)
        raise DocumentExtractionError("Unsupported document type")

    @staticmethod
    def _decode_text(content: bytes) -> str:
        if b"\x00" in content:
            raise DocumentExtractionError("Text documents cannot contain null bytes")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("Text documents must be valid UTF-8") from exc
        if not text.strip():
            raise DocumentExtractionError("Document contains no text")
        return text

    @staticmethod
    def _extract_pdf(content: bytes) -> list[ExtractedPage]:
        if not content.startswith(b"%PDF-"):
            raise DocumentExtractionError("PDF file signature is invalid")
        try:
            reader = PdfReader(BytesIO(content))
            pages = [
                ExtractedPage(content=(page.extract_text() or "").strip(), page_number=index)
                for index, page in enumerate(reader.pages, start=1)
            ]
        except (PdfReadError, ValueError, OSError) as exc:
            raise DocumentExtractionError("PDF could not be read safely") from exc
        pages = [page for page in pages if page.content]
        if not pages:
            raise DocumentExtractionError("PDF contains no extractable text")
        return pages
