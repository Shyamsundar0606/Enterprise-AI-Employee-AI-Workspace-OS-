"""Deterministic chunking with bounded overlap."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.document_extraction import ExtractedPage


@dataclass(frozen=True)
class TextChunk:
    content: str
    chunk_index: int
    page_number: int | None


class TextChunker:
    def __init__(self, *, chunk_size: int, overlap: int) -> None:
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("Chunk overlap must be non-negative and smaller than chunk size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, pages: list[ExtractedPage]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for page in pages:
            text = page.content.strip()
            start = 0
            while start < len(text):
                content = text[start : start + self.chunk_size].strip()
                if content:
                    chunks.append(
                        TextChunk(
                            content=content,
                            chunk_index=len(chunks),
                            page_number=page.page_number,
                        )
                    )
                if start + self.chunk_size >= len(text):
                    break
                start += self.chunk_size - self.overlap
        return chunks
