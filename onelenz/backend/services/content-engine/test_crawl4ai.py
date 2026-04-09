"""Crawl4AI test script — save markdown output to files."""
import asyncio
import os

from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    CacheMode,
    BestFirstCrawlingStrategy,
    KeywordRelevanceScorer,
    DefaultMarkdownGenerator,
    PruningContentFilter,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "test_output")


async def test_raw_vs_fit():
    """Compare raw_markdown vs fit_markdown — save both."""
    print("=" * 60)
    print("TEST 1: raw vs fit (about-us page)")
    print("=" * 60)

    # Without filter
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.rapyder.com/about-us/",
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS),
        )
        raw_no_filter = result.markdown.raw_markdown
        fit_no_filter = result.markdown.fit_markdown or ""

    # With PruningContentFilter
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.6),
        options={"ignore_links": True},
    )
    config = CrawlerRunConfig(
        markdown_generator=md_generator,
        excluded_tags=["nav", "footer", "header", "aside"],
        remove_overlay_elements=True,
        cache_mode=CacheMode.BYPASS,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.rapyder.com/about-us/",
            config=config,
        )
        raw_with_filter = result.markdown.raw_markdown
        fit_with_filter = result.markdown.fit_markdown or ""

    _save("01_about_raw_no_filter.md", raw_no_filter)
    _save("01_about_fit_no_filter.md", fit_no_filter)
    _save("01_about_raw_with_filter.md", raw_with_filter)
    _save("01_about_fit_with_filter.md", fit_with_filter)

    print(f"  raw (no filter):   {len(raw_no_filter):,} chars")
    print(f"  fit (no filter):   {len(fit_no_filter):,} chars")
    print(f"  raw (with filter): {len(raw_with_filter):,} chars")
    print(f"  fit (with filter): {len(fit_with_filter):,} chars")


async def test_case_studies():
    """Crawl case studies listing page."""
    print("\n" + "=" * 60)
    print("TEST 2: case-studies page (PruningContentFilter)")
    print("=" * 60)

    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.6),
        options={"ignore_links": True},
    )
    config = CrawlerRunConfig(
        markdown_generator=md_generator,
        excluded_tags=["nav", "footer", "header", "aside"],
        remove_overlay_elements=True,
        cache_mode=CacheMode.BYPASS,
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url="https://www.rapyder.com/case-studies/",
            config=config,
        )

    _save("02_case_studies_raw.md", result.markdown.raw_markdown)
    _save("02_case_studies_fit.md", result.markdown.fit_markdown or "")

    print(f"  raw: {len(result.markdown.raw_markdown):,} chars")
    print(f"  fit: {len(result.markdown.fit_markdown or ''):,} chars")


async def test_best_first_crawl():
    """Multi-page crawl — save each page separately."""
    print("\n" + "=" * 60)
    print("TEST 3: BestFirst multi-page (rapyder.com, 5 pages)")
    print("=" * 60)

    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.6),
        options={"ignore_links": True},
    )

    config = CrawlerRunConfig(
        deep_crawl_strategy=BestFirstCrawlingStrategy(
            max_depth=1,
            max_pages=5,
            url_scorer=KeywordRelevanceScorer(
                keywords=[
                    "case-study", "services", "solutions",
                    "about", "cloud", "aws",
                ]
            ),
        ),
        markdown_generator=md_generator,
        excluded_tags=["nav", "footer", "header", "aside"],
        remove_overlay_elements=True,
        stream=True,
        page_timeout=30000,
        cache_mode=CacheMode.BYPASS,
    )

    index = []
    page_num = 0

    async with AsyncWebCrawler() as crawler:
        async for result in await crawler.arun(
            "https://www.rapyder.com/", config=config
        ):
            if result.success:
                depth = result.metadata.get("depth", 0)
                score = result.metadata.get("score", 0)
                raw = result.markdown.raw_markdown
                fit = result.markdown.fit_markdown or ""

                fname = f"03_page_{page_num:02d}.md"
                content = (
                    f"<!-- URL: {result.url} -->\n"
                    f"<!-- Depth: {depth} | Score: {score:.2f} -->\n"
                    f"<!-- Raw: {len(raw):,} chars | "
                    f"Fit: {len(fit):,} chars -->\n\n"
                    f"# FIT MARKDOWN\n\n{fit}\n\n"
                    f"---\n\n"
                    f"# RAW MARKDOWN\n\n{raw}\n"
                )
                _save(fname, content)

                index.append(
                    f"- [{fname}]({fname}) — {result.url} "
                    f"(depth={depth}, score={score:.2f}, "
                    f"fit={len(fit):,} chars)"
                )
                print(
                    f"  ✅ [{page_num}] depth={depth} "
                    f"score={score:.2f} "
                    f"fit={len(fit):,} | {result.url}"
                )
                page_num += 1
            else:
                print(f"  ❌ {result.url}")

    _save("03_index.md", "# Crawled Pages\n\n" + "\n".join(index))
    print(f"\n  Total: {page_num} pages saved")


def _save(filename: str, content: str) -> None:
    """Save content to test_output directory."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w") as f:
        f.write(content)
    print(f"  → Saved {filename} ({len(content):,} chars)")


async def main():
    print("Crawl4AI Output Test")
    print(f"Output dir: {OUTPUT_DIR}\n")

    await test_raw_vs_fit()
    await test_case_studies()
    await test_best_first_crawl()

    print("\n" + "=" * 60)
    print(f"All output saved to: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
