"""Structure-aware chunking via Docling HybridChunker.

Best practices applied:
- MarkdownTableSerializer for readable table chunks
- chunker.contextualize() to prepend heading context
  to each chunk before embedding
- Page number extraction from Docling provenance
- Defensive metadata extraction (hasattr/getattr)
"""
from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module="docling"
)

from typing import Any

from shared.logging import get_logger

from ..config import settings

logger = get_logger(__name__)

# Element types to skip during chunking — these are
# repeated noise (page headers/footers/footnotes)
_SKIP_ELEMENT_TYPES = frozenset({
    "PageHeaderItem",
    "PageFooterItem",
    "FootnoteItem",
})

# Cached chunker instance (lazy-initialized)
_chunker: Any = None


def _get_chunker() -> Any:
    """Create or return cached HybridChunker.

    Uses MarkdownTableSerializer so tables are
    serialized as markdown (better for embedding)
    instead of Docling's default triplet format.
    """
    global _chunker
    if _chunker is not None:
        return _chunker

    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.hierarchical_chunker import (
        ChunkingDocSerializer,
        ChunkingSerializerProvider,
    )
    from docling_core.transforms.serializer.markdown import (
        MarkdownTableSerializer,
    )

    class _MDTableProvider(ChunkingSerializerProvider):
        def get_serializer(self, *, doc: Any) -> Any:
            return ChunkingDocSerializer(
                doc=doc,
                table_serializer=MarkdownTableSerializer(),
            )

    _chunker = HybridChunker(
        max_tokens=settings.chunk_max_tokens,
        merge_peers=True,
        serializer_provider=_MDTableProvider(),
    )
    return _chunker


def _extract_chunks(
    docling_document: Any,
    file_type: str | None = None,
) -> list[dict]:
    """Run HybridChunker on a DoclingDocument.

    For each chunk:
    - Uses contextualize() to get heading-enriched
      text (prepends section headers for better
      embedding quality)
    - Extracts metadata: headings, captions, page,
      element type
    """
    chunker = _get_chunker()
    chunks = list(chunker.chunk(docling_document))

    doc_title = _extract_doc_title(docling_document)
    result = []
    skipped = 0
    chunk_index = 0

    for chunk in chunks:
        element_type = _detect_element_type(chunk)

        # Skip page headers/footers — repeated noise
        if element_type in _SKIP_ELEMENT_TYPES:
            skipped += 1
            continue

        # contextualize() prepends section headings
        # to the chunk text — better for embedding
        # e.g., "Solutions > Cloud Migration\n\n..."
        contextualized = chunker.contextualize(
            chunk=chunk
        )
        # Fall back to raw text if contextualize fails
        text = contextualized or chunk.text

        # Skip empty/whitespace-only chunks
        if not text.strip():
            skipped += 1
            continue

        heading = _get_heading(chunk)
        caption = _get_caption(chunk)
        page_no = _get_page_number(chunk)

        metadata: dict[str, Any] = {
            "doc_title": doc_title,
            "element_type": element_type,
            "file_type": file_type,
        }
        if caption:
            metadata["caption"] = caption
        if page_no is not None:
            metadata["page_no"] = page_no

        result.append({
            "chunk_index": chunk_index,
            "content_text": text,
            "section_heading": heading,
            "token_count": _count_tokens(text),
            "metadata": metadata,
        })
        chunk_index += 1

    if skipped:
        logger.info(
            "Skipped %d chunks (headers/footers/empty)",
            skipped,
        )

    logger.info(
        "Chunked into %d chunks (type=%s)",
        len(result),
        file_type or "MD",
    )
    return result


def chunk_document(
    docling_document: Any,
    file_type: str | None = None,
) -> list[dict]:
    """Chunk a DoclingDocument from file extraction.

    Args:
        docling_document: Docling DoclingDocument.
        file_type: Original file type (PDF, DOCX, etc.)

    Returns:
        List of chunk dicts with content_text,
        section_heading, token_count, metadata.
    """
    return _extract_chunks(docling_document, file_type)


def chunk_markdown(
    markdown_text: str,
    source_url: str | None = None,
    page_title: str | None = None,
) -> list[dict]:
    """Chunk markdown text (from Crawl4AI).

    Converts markdown to DoclingDocument via
    convert_string, then uses HybridChunker —
    same structure-aware chunking as files.

    Args:
        markdown_text: Clean markdown from Crawl4AI.
        source_url: URL of the page (for metadata).
        page_title: Page title (for metadata).
    """
    from docling.datamodel.base_models import (
        InputFormat,
    )
    from docling.document_converter import (
        DocumentConverter,
    )

    converter = DocumentConverter()
    result = converter.convert_string(
        content=markdown_text,
        format=InputFormat.MD,
        name=page_title or source_url or "web_page",
    )
    doc = result.document

    chunks = _extract_chunks(doc, file_type="HTML")

    # Add source_url to each chunk (top-level + metadata)
    if source_url:
        for chunk in chunks:
            chunk["source_url"] = source_url
            chunk["metadata"]["source_url"] = source_url

    return chunks


# ── metadata helpers ────────────────────────────


def _get_heading(chunk: Any) -> str | None:
    """Extract heading path from chunk metadata.

    Returns joined heading path like
    "Solutions / Cloud Migration".
    """
    meta = getattr(chunk, "meta", None)
    if meta is None:
        return None
    headings = getattr(meta, "headings", None)
    if headings:
        return " / ".join(headings)
    return None


def _get_caption(chunk: Any) -> str | None:
    """Extract first caption from chunk metadata."""
    meta = getattr(chunk, "meta", None)
    if meta is None:
        return None
    captions = getattr(meta, "captions", None)
    if captions:
        return captions[0]
    return None


def _get_page_number(chunk: Any) -> int | None:
    """Extract page number from chunk provenance."""
    meta = getattr(chunk, "meta", None)
    if meta is None:
        return None
    doc_items = getattr(meta, "doc_items", None)
    if not doc_items:
        return None
    prov = getattr(doc_items[0], "prov", None)
    if prov and len(prov) > 0:
        return getattr(prov[0], "page_no", None)
    return None


def _extract_doc_title(document: Any) -> str | None:
    """Extract document title from Docling doc."""
    if hasattr(document, "title") and document.title:
        return str(document.title)
    return None


def _detect_element_type(chunk: Any) -> str:
    """Detect chunk element type from Docling metadata.

    Returns class name of the first doc_item,
    e.g., "TableItem", "TextItem", "PictureItem".
    """
    meta = getattr(chunk, "meta", None)
    if meta is None:
        return "unknown"
    doc_items = getattr(meta, "doc_items", None)
    if doc_items:
        return type(doc_items[0]).__name__
    return "paragraph"


def _count_tokens(text: str) -> int:
    """Approximate token count by whitespace split."""
    return len(text.split())


