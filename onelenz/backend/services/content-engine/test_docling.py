"""Docling test script — test extraction + chunking with real docs.

Usage:
    python3 test_docling.py /path/to/document.pdf
    python3 test_docling.py /path/to/document.pdf --ocr
    python3 test_docling.py /path/to/presentation.pptx
    python3 test_docling.py /path/to/spreadsheet.xlsx
    python3 test_docling.py /path/to/document.docx
    python3 test_docling.py /path/to/file.txt
    python3 test_docling.py --markdown "# Some markdown text"
    python3 test_docling.py --crawl4ai-output [path-to-md-file]
"""
import json
import os
import sys
import warnings
from io import BytesIO

warnings.filterwarnings("ignore", category=DeprecationWarning)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "test_output")


def save(filename: str, content: str) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w") as f:
        f.write(content)
    print(f"  → Saved {filename} ({len(content):,} chars)")


def get_chunker():
    """Create HybridChunker with MarkdownTableSerializer."""
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.hierarchical_chunker import (
        ChunkingDocSerializer,
        ChunkingSerializerProvider,
    )
    from docling_core.transforms.serializer.markdown import (
        MarkdownTableSerializer,
    )

    class MDTableProvider(ChunkingSerializerProvider):
        def get_serializer(self, *, doc):
            return ChunkingDocSerializer(
                doc=doc,
                table_serializer=MarkdownTableSerializer(),
            )

    return HybridChunker(
        max_tokens=512,
        merge_peers=True,
        serializer_provider=MDTableProvider(),
    )


def _merge_small(
    chunks: list[dict],
    min_tokens: int = 50,
    max_tokens: int = 512,
) -> list[dict]:
    """Merge consecutive undersized chunks.

    Rules:
    - Only merge if buffer is under min_tokens
    - Don't merge if result would exceed max_tokens
    - Always merge forward (small chunk joins the next)
    """
    if not chunks:
        return chunks

    merged: list[dict] = []
    buffer: dict | None = None

    for chunk in chunks:
        if buffer is None:
            buffer = chunk.copy()
            continue

        combined_tokens = buffer["token_count"] + chunk["token_count"]

        if (
            buffer["token_count"] < min_tokens
            and combined_tokens <= max_tokens
        ):
            # Merge: append chunk into buffer
            buffer["content_text"] += "\n\n" + chunk["content_text"]
            buffer["token_count"] = combined_tokens
            # Combine headings if different
            if (
                chunk["section_heading"]
                and chunk["section_heading"] != buffer["section_heading"]
            ):
                buffer["section_heading"] = (
                    (buffer["section_heading"] or "")
                    + " / "
                    + chunk["section_heading"]
                )
        else:
            merged.append(buffer)
            buffer = chunk.copy()

    if buffer:
        merged.append(buffer)

    # Re-index
    for i, c in enumerate(merged):
        c["chunk_index"] = i

    return merged


def print_chunk_summary(chunks, chunker):
    """Print and save chunk details."""
    chunk_output = []

    for i, chunk in enumerate(chunks):
        ctx_text = chunker.contextualize(chunk=chunk)
        raw_text = chunk.text

        meta = getattr(chunk, "meta", None)
        headings = list(meta.headings or []) if meta else []
        captions = list(meta.captions or []) if meta else []
        doc_items = list(meta.doc_items or []) if meta else []

        element_type = "unknown"
        page_no = None
        if doc_items:
            element_type = type(doc_items[0]).__name__
            prov = getattr(doc_items[0], "prov", [])
            if prov:
                page_no = getattr(prov[0], "page_no", None)

        token_count = len(raw_text.split())
        ctx_token_count = len(ctx_text.split()) if ctx_text else 0

        chunk_output.append({
            "index": i,
            "element_type": element_type,
            "headings": headings,
            "captions": captions,
            "page_no": page_no,
            "raw_tokens": token_count,
            "ctx_tokens": ctx_token_count,
        })

        heading_str = " / ".join(headings) if headings else "-"
        page_str = str(page_no) if page_no is not None else "-"
        print(
            f"  [{i:3d}] {element_type:<15s} "
            f"page={page_str:>3s} "
            f"tokens={token_count:>4d} "
            f"ctx={ctx_token_count:>4d} "
            f"| {heading_str}"
        )

    # Summary stats
    token_counts = [c["raw_tokens"] for c in chunk_output]
    print(f"\n  Summary:")
    print(f"    Chunks: {len(chunks)}")
    print(f"    Min tokens: {min(token_counts)}")
    print(f"    Max tokens: {max(token_counts)}")
    print(f"    Avg tokens: {sum(token_counts) // len(token_counts)}")

    types: dict[str, int] = {}
    for c in chunk_output:
        t = c["element_type"]
        types[t] = types.get(t, 0) + 1
    print(f"    Element types:")
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"      {t}: {count}")

    return chunk_output


def test_file_extraction(
    file_path: str, enable_ocr: bool = False,
) -> None:
    """Test Docling file extraction + chunking."""
    from docling.datamodel.base_models import (
        DocumentStream,
        InputFormat,
    )
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
    )
    from docling.document_converter import (
        DocumentConverter,
        PdfFormatOption,
    )

    file_name = os.path.basename(file_path)
    file_ext = file_name.rsplit(".", 1)[-1].upper()
    prefix = file_ext.lower()

    print("=" * 60)
    print(f"FILE: {file_name} ({file_ext})")
    print(f"OCR: {'enabled' if enable_ocr else 'disabled'}")
    print("=" * 60)

    # 1. Extract using DocumentStream (bytes, no temp file)
    print("\n[1] Extracting with Docling (DocumentStream)...")

    with open(file_path, "rb") as f:
        file_bytes = f.read()
    print(f"  File size: {len(file_bytes):,} bytes")

    format_options = {}
    if file_ext == "PDF":
        pdf_opts = PdfPipelineOptions(
            do_table_structure=True,
            do_ocr=enable_ocr,
        )
        format_options[InputFormat.PDF] = PdfFormatOption(
            pipeline_options=pdf_opts,
        )

    converter = DocumentConverter(
        format_options=format_options,
    )

    source = DocumentStream(
        name=file_name,
        stream=BytesIO(file_bytes),
    )
    result = converter.convert(
        source,
        max_num_pages=200,
        max_file_size=52_428_800,
    )
    doc = result.document

    # Save full markdown export
    md_export = doc.export_to_markdown()
    save(f"{prefix}_full_markdown.md", md_export)
    print(f"  Full markdown: {len(md_export):,} chars")

    # Document metadata
    title = getattr(doc, "title", None)
    num_pages_attr = getattr(doc, "num_pages", None)
    num_pages = num_pages_attr() if callable(num_pages_attr) else num_pages_attr
    print(f"  Title: {title or 'N/A'}")
    print(f"  Pages: {num_pages or len(doc.pages)}")

    # 2. Chunk
    print("\n[2] Chunking with HybridChunker + MarkdownTableSerializer...")
    chunker = get_chunker()
    raw_chunks = list(chunker.chunk(doc))
    print(f"  Raw chunks: {len(raw_chunks)}")
    chunk_output = print_chunk_summary(raw_chunks, chunker)

    # 3. Convert to dicts for merge
    chunk_dicts = []
    for i, chunk in enumerate(raw_chunks):
        ctx = chunker.contextualize(chunk=chunk)
        meta = getattr(chunk, "meta", None)
        headings = list(meta.headings or []) if meta else []
        doc_items = list(meta.doc_items or []) if meta else []
        element_type = type(doc_items[0]).__name__ if doc_items else "unknown"
        page_no = None
        if doc_items:
            prov = getattr(doc_items[0], "prov", [])
            if prov:
                page_no = getattr(prov[0], "page_no", None)

        chunk_dicts.append({
            "chunk_index": i,
            "content_text": ctx or chunk.text,
            "raw_text": chunk.text,
            "section_heading": " / ".join(headings) if headings else None,
            "token_count": len((ctx or chunk.text).split()),
            "element_type": element_type,
            "page_no": page_no,
        })

    # Save raw chunks (before merge)
    raw_md = []
    for c in chunk_dicts:
        raw_md.append(
            f"## Chunk {c['chunk_index']}\n"
            f"<!-- type: {c['element_type']} | "
            f"page: {c['page_no']} | "
            f"headings: {c['section_heading'] or 'none'} | "
            f"tokens: {c['token_count']} -->\n\n"
            f"{c['content_text']}\n\n---\n"
        )
    save(f"{prefix}_chunks_raw.md", "\n".join(raw_md))

    # 4. Merge small chunks
    MIN_TOKENS = 50
    MAX_MERGED = 512
    print(f"\n[3] Merging small chunks (min={MIN_TOKENS}, max={MAX_MERGED})...")

    merged = _merge_small(chunk_dicts, MIN_TOKENS, MAX_MERGED)

    print(f"  Before: {len(chunk_dicts)} → After: {len(merged)}")
    print()
    for c in merged:
        heading = c["section_heading"] or "-"
        print(
            f"  [{c['chunk_index']:3d}] {c['element_type']:<15s} "
            f"tokens={c['token_count']:>4d} "
            f"| {heading}"
        )

    # Save merged chunks
    merged_md = []
    for c in merged:
        merged_md.append(
            f"## Chunk {c['chunk_index']}\n"
            f"<!-- type: {c['element_type']} | "
            f"page: {c['page_no']} | "
            f"headings: {c['section_heading'] or 'none'} | "
            f"tokens: {c['token_count']} -->\n\n"
            f"{c['content_text']}\n\n---\n"
        )
    save(f"{prefix}_chunks.md", "\n".join(merged_md))
    save(
        f"{prefix}_chunks_meta.json",
        json.dumps(chunk_output, indent=2, default=str),
    )


def test_markdown_chunking(markdown_text: str, label: str = "md") -> None:
    """Test markdown → DoclingDocument → HybridChunker."""
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat

    print("=" * 60)
    print(f"MARKDOWN INPUT ({label})")
    print("=" * 60)

    # 1. Convert markdown to DoclingDocument
    print("\n[1] Converting markdown → DoclingDocument...")
    converter = DocumentConverter()
    result = converter.convert_string(
        content=markdown_text,
        format=InputFormat.MD,
        name=label,
    )
    doc = result.document
    print(f"  Input: {len(markdown_text):,} chars")

    # 2. Chunk
    print("\n[2] Chunking...")
    chunker = get_chunker()
    chunks = list(chunker.chunk(doc))
    chunk_output = print_chunk_summary(chunks, chunker)

    # 3. Save
    chunks_md = []
    for i, chunk in enumerate(chunks):
        ctx = chunker.contextualize(chunk=chunk)
        meta = getattr(chunk, "meta", None)
        headings = getattr(meta, "headings", []) if meta else []
        tokens = len(chunk.text.split())

        chunks_md.append(
            f"## Chunk {i}\n"
            f"<!-- headings: {' / '.join(headings) if headings else 'none'}"
            f" | tokens: {tokens} -->\n\n"
            f"### Raw\n{chunk.text}\n\n"
            f"### Contextualized\n{ctx or 'N/A'}\n\n---\n"
        )

    save(f"{label}_chunks.md", "\n".join(chunks_md))
    save(
        f"{label}_chunks_meta.json",
        json.dumps(chunk_output, indent=2, default=str),
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--markdown":
        if len(sys.argv) < 3:
            print("Usage: python3 test_docling.py --markdown \"# text\"")
            sys.exit(1)
        test_markdown_chunking(sys.argv[2])

    elif sys.argv[1] == "--crawl4ai-output":
        path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
            OUTPUT_DIR, "01_about_fit_with_filter.md"
        )
        with open(path) as f:
            md = f.read()
        label = os.path.basename(path).replace(".md", "")
        print(f"Reading: {path} ({len(md):,} chars)")
        test_markdown_chunking(md, label=label)

    else:
        file_path = sys.argv[1]
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            sys.exit(1)
        enable_ocr = "--ocr" in sys.argv
        test_file_extraction(file_path, enable_ocr=enable_ocr)

    print(f"\nAll output in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
