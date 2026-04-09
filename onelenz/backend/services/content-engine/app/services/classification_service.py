"""Auto-classification via embedding similarity."""
from __future__ import annotations

from shared.logging import get_logger

logger = get_logger(__name__)

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "MARKETING_COLLATERAL": (
        "marketing collateral brochure datasheet"
        " whitepaper flyer"
    ),
    "SOW_PROJECT_DOC": (
        "statement of work project document scope"
        " deliverable timeline"
    ),
    "PRODUCT_WORKBOOK": (
        "product workbook catalog specifications"
        " features pricing sheet"
    ),
    "CASE_STUDY": (
        "customer case study success story challenge"
        " solution results outcomes"
    ),
    "BLOG": (
        "blog post article thought leadership"
        " opinion editorial"
    ),
    "PRESS_RELEASE": (
        "press release announcement official news"
        " media coverage"
    ),
    "WEBSITE_PAGE": (
        "homepage website company about services"
        " landing page"
    ),
    "SOCIAL_MEDIA": (
        "social media post linkedin twitter"
        " facebook company page"
    ),
}

# Cached category embeddings (lazy-initialized)
_category_embeddings: dict[str, list[float]] | None = None


async def init_category_embeddings() -> None:
    """Pre-compute category embeddings via Titan V2.

    Called once on first classification request.
    Caches in memory for the process lifetime.
    """
    global _category_embeddings
    if _category_embeddings is not None:
        return

    from .embedding_service import embed_batch

    categories = list(CATEGORY_DESCRIPTIONS.keys())
    descriptions = list(CATEGORY_DESCRIPTIONS.values())

    embeddings = await embed_batch(descriptions)

    _category_embeddings = dict(
        zip(categories, embeddings)
    )
    logger.info(
        "Initialized %d category embeddings",
        len(_category_embeddings),
    )


def _cosine_similarity(
    a: list[float], b: list[float]
) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def classify(
    embedding: list[float],
) -> str:
    """Classify a document by its embedding.

    Compares against cached category embeddings.
    Returns the best matching category_id.
    """
    await init_category_embeddings()
    assert _category_embeddings is not None

    best_cat = "MARKETING_COLLATERAL"
    best_score = -1.0

    for cat, cat_emb in _category_embeddings.items():
        score = _cosine_similarity(embedding, cat_emb)
        if score > best_score:
            best_score = score
            best_cat = cat

    logger.info(
        "Classified as %s (score=%.3f)",
        best_cat, best_score,
    )
    return best_cat


async def classify_website_pages(
    page_embeddings: list[list[float]],
) -> tuple[str, dict[int, str]]:
    """Classify each page of a website scrape.

    Returns:
        (dominant_category, {page_index: category_id})
    """
    await init_category_embeddings()
    assert _category_embeddings is not None

    per_page: dict[int, str] = {}
    category_counts: dict[str, int] = {}

    for i, emb in enumerate(page_embeddings):
        best_cat = "MARKETING_COLLATERAL"
        best_score = -1.0
        for cat, cat_emb in (
            _category_embeddings.items()
        ):
            score = _cosine_similarity(emb, cat_emb)
            if score > best_score:
                best_score = score
                best_cat = cat
        per_page[i] = best_cat
        category_counts[best_cat] = (
            category_counts.get(best_cat, 0) + 1
        )

    # Dominant = most frequent
    dominant = max(
        category_counts,
        key=lambda k: category_counts[k],
    )

    logger.info(
        "Website classified: dominant=%s, pages=%d",
        dominant, len(page_embeddings),
    )
    return dominant, per_page
