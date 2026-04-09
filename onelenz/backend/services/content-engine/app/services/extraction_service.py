"""Text extraction via Docling (files) and Crawl4AI (URLs)."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from shared.errors import AppError
from shared.errors.codes import CONTENT_INVALID_URL
from shared.logging import get_logger

from ..config import settings

logger = get_logger(__name__)

# ── URL safety ──────────────────────────────────

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_safe_url(url: str) -> bool:
    """Validate URL is a public domain, not an IP
    or internal address.

    1. Must have a proper domain with TLD (no raw IPs)
    2. Resolved IP must not be private/internal
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False

    # Block raw IPs (v4 and v6)
    try:
        ipaddress.ip_address(hostname)
        return False
    except ValueError:
        pass

    # Block localhost aliases
    if hostname in ("localhost", "0.0.0.0"):
        return False

    # Must have at least one dot (domain.tld)
    if "." not in hostname:
        return False

    # DNS resolution check — block domains
    # pointing to private IPs
    try:
        resolved_ip = ipaddress.ip_address(
            socket.gethostbyname(hostname)
        )
        if any(
            resolved_ip in net
            for net in _BLOCKED_NETWORKS
        ):
            return False
    except socket.gaierror:
        return False

    return True


def _build_crawl_config(
    deep_crawl_strategy: object | None = None,
    stream: bool = False,
) -> object:
    """Build CrawlerRunConfig with PruningContentFilter.

    Centralises Crawl4AI config so both extract_url
    and extract_website use the same quality settings.
    """
    from crawl4ai import (
        CacheMode,
        CrawlerRunConfig,
        DefaultMarkdownGenerator,
        PruningContentFilter,
    )

    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=settings.crawl_content_filter_threshold,
        ),
        options={"ignore_links": True},
    )

    kwargs: dict = {
        "markdown_generator": md_generator,
        "excluded_tags": [
            "nav", "footer", "header", "aside",
        ],
        "remove_overlay_elements": True,
        "page_timeout": settings.crawl_timeout_seconds * 1000,
        "cache_mode": CacheMode.BYPASS,
    }
    if deep_crawl_strategy is not None:
        kwargs["deep_crawl_strategy"] = deep_crawl_strategy
        kwargs["stream"] = stream

    return CrawlerRunConfig(**kwargs)


def _get_markdown(result: object) -> str:
    """Extract best markdown from a CrawlResult.

    Prefers fit_markdown (pruned) over raw_markdown.
    """
    md = getattr(result, "markdown", None)
    if md is None:
        return ""
    fit = getattr(md, "fit_markdown", None)
    if fit:
        return fit
    raw = getattr(md, "raw_markdown", None)
    return raw or ""


def _get_links(result: object) -> list[str]:
    """Extract internal links from a CrawlResult."""
    links = getattr(result, "links", {})
    if isinstance(links, dict):
        internal = links.get("internal", [])
        return [
            link["href"]
            for link in internal
            if isinstance(link, dict) and "href" in link
        ]
    return []


async def extract_file(
    file_bytes: bytes,
    file_name: str,
    file_type: str,
) -> dict:
    """Extract text from a document file using Docling.

    Uses DocumentStream to process bytes directly
    (no temp file needed). Enables table structure
    extraction for PDFs.

    Args:
        file_bytes: Raw file content.
        file_name: Original filename.
        file_type: File extension (PDF, DOCX, etc.)

    Returns:
        {
            "document": DoclingDocument object,
            "page_count": int,
        }
    """
    from io import BytesIO

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

    def _convert() -> object:
        # Enable table structure for PDFs
        format_options = {}
        if file_type.upper() == "PDF":
            pdf_opts = PdfPipelineOptions(
                do_table_structure=True,
                do_ocr=settings.docling_enable_ocr,
            )
            format_options[InputFormat.PDF] = (
                PdfFormatOption(
                    pipeline_options=pdf_opts,
                )
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
            max_num_pages=(
                settings.docling_max_num_pages
            ),
            max_file_size=(
                settings.docling_max_file_size
            ),
        )
        return result.document

    document = await asyncio.to_thread(_convert)
    num_pages_attr = getattr(document, "num_pages", None)
    if callable(num_pages_attr):
        page_count = num_pages_attr() or 1
    elif num_pages_attr:
        page_count = int(num_pages_attr)
    else:
        page_count = len(getattr(document, "pages", {})) or 1
    logger.info(
        "Extracted file: %s, pages: %d",
        file_name,
        page_count,
    )
    return {
        "document": document,
        "page_count": page_count,
    }


async def extract_url(url: str) -> dict:
    """Extract content from a single URL using Crawl4AI.

    Uses PruningContentFilter + excluded_tags for
    clean markdown output. Prefers fit_markdown.

    Returns:
        {
            "pages": [{"url": str, "markdown": str}],
            "links": [str],
            "page_count": 1,
        }
    """
    from crawl4ai import AsyncWebCrawler

    config = _build_crawl_config()

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url, config=config
        )

    markdown = _get_markdown(result)
    links = _get_links(result)

    logger.info(
        "Extracted URL: %s, markdown: %d chars",
        url,
        len(markdown),
    )
    return {
        "pages": [{"url": url, "markdown": markdown}],
        "links": links,
        "page_count": 1,
    }


async def extract_website(url: str) -> dict:
    """Crawl a website using BestFirst strategy.

    Uses KeywordRelevanceScorer to prioritise
    relevant pages. PruningContentFilter strips
    nav/footer/boilerplate from each page.

    Returns:
        {
            "pages": [
                {"url": str, "markdown": str}, ...
            ],
            "page_count": int,
        }
    """
    from crawl4ai import (
        AsyncWebCrawler,
        BestFirstCrawlingStrategy,
    )

    strategy = BestFirstCrawlingStrategy(
        max_depth=settings.crawl_max_depth,
        max_pages=settings.crawl_max_pages,
        include_external=False,
    )
    config = _build_crawl_config(
        deep_crawl_strategy=strategy,
        stream=True,
    )

    pages: list[dict] = []

    async with AsyncWebCrawler() as crawler:
        async for result in await crawler.arun(
            url=url, config=config
        ):
            if not result.success:
                logger.warning(
                    "Failed to crawl: %s — %s",
                    result.url,
                    result.error_message,
                )
                continue

            markdown = _get_markdown(result)
            if not markdown.strip():
                continue

            depth = result.metadata.get("depth", 0)
            score = result.metadata.get("score", 0)
            pages.append({
                "url": result.url,
                "markdown": markdown,
            })
            logger.info(
                "Crawled page: depth=%d score=%.2f "
                "len=%d | %s",
                depth,
                score,
                len(markdown),
                result.url,
            )

    logger.info(
        "Crawled website: %s, pages: %d",
        url,
        len(pages),
    )
    return {"pages": pages, "page_count": len(pages)}


def detect_source_type_from_url(url: str) -> str:
    """Phase 1 detection -- URL structure only.

    No network call. Quick sync check.
    Returns "WEBSITE_SCRAPE" or "URL".
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if path == "" or path == "index.html":
        return "WEBSITE_SCRAPE"

    return "URL"


def reclassify_if_listing(
    url: str, discovered_links: list[str]
) -> str:
    """Phase 2 detection -- listing page check.

    Called inside Celery task after page fetch.
    If many child links under same path, it's a listing.
    """
    threshold = settings.crawl_listing_link_threshold
    prefix = url.rstrip("/") + "/"
    child_count = sum(
        1
        for link in discovered_links
        if link.startswith(prefix)
    )
    if child_count > threshold:
        return "WEBSITE_SCRAPE"
    return "URL"


async def check_url_reachable(url: str) -> bool:
    """Validate URL safety then HEAD request.

    Raises AppError if URL points to private/internal
    address. Returns True if reachable (2xx/3xx).
    """
    if not _is_safe_url(url):
        raise AppError(CONTENT_INVALID_URL)

    try:
        async with httpx.AsyncClient(
            timeout=5.0, follow_redirects=True
        ) as client:
            resp = await client.head(url)
            return resp.status_code < 400
    except (httpx.RequestError, httpx.HTTPStatusError):
        return False
