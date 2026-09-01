import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable

SHORT_PDF_PAGE_LIMIT = 15
LONG_PDF_OVERVIEW_PAGES = 2
LONG_PDF_OVERVIEW_CHARS = 12_000
MAX_SEARCH_RESULTS = 8
MAX_EXACT_PAGES = 8
MAX_EXACT_CHARS = 30_000
SEARCH_SNIPPET_CHARS = 700

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "in", "is", "it", "of", "on", "or", "our", "that",
    "the", "their", "this", "to", "was", "were", "which", "with",
}


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOP_WORDS and len(token) > 1
    ]


@lru_cache(maxsize=16)
def _cached_pdf_pages(
    resolved_path: str,
    modified_time_ns: int,
    file_size: int,
) -> tuple[str, ...]:
    del modified_time_ns, file_size
    from pypdf import PdfReader

    reader = PdfReader(resolved_path)
    return tuple((page.extract_text() or "").strip() for page in reader.pages)


def _load_pdf_pages(file_path: str) -> tuple[str, ...]:
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File '{file_path}' not found.")
    stat = path.stat()
    return _cached_pdf_pages(str(path), stat.st_mtime_ns, stat.st_size)


def _rank_pages(
    page_texts: Iterable[str],
    query: str,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[tuple[int, float]]:
    pages = list(page_texts)
    query_terms = list(dict.fromkeys(_tokens(query)))
    if not pages or not query_terms:
        return []

    document_tokens = [_tokens(page) for page in pages]
    document_counts = [Counter(tokens) for tokens in document_tokens]
    document_frequency = Counter()
    for counts in document_counts:
        document_frequency.update(counts.keys())

    page_count = len(pages)
    average_length = sum(len(tokens) for tokens in document_tokens) / page_count
    average_length = average_length or 1.0
    query_phrase = " ".join(query.lower().split())
    ranked = []

    for page_index, (page, tokens, counts) in enumerate(
        zip(pages, document_tokens, document_counts),
        start=1,
    ):
        if not tokens:
            continue

        score = 0.0
        matched_terms = 0
        for term in query_terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            matched_terms += 1
            frequency_in_pages = document_frequency[term]
            inverse_frequency = math.log(
                1 + (page_count - frequency_in_pages + 0.5) / (frequency_in_pages + 0.5)
            )
            length_adjustment = 1.2 * (0.25 + 0.75 * len(tokens) / average_length)
            score += inverse_frequency * frequency * 2.2 / (frequency + length_adjustment)

        if matched_terms:
            score += 1.5 * matched_terms / len(query_terms)
        normalized_page = " ".join(page.lower().split())
        if len(query_phrase) >= 8 and query_phrase in normalized_page:
            score += 4.0
        if score > 0:
            ranked.append((page_index, score))

    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[:max_results]


def _best_snippet(page_text: str, query: str) -> str:
    clean_text = " ".join(page_text.split())
    if len(clean_text) <= SEARCH_SNIPPET_CHARS:
        return clean_text

    lowered = clean_text.lower()
    query_terms = _tokens(query)
    candidate_starts = []
    for term in query_terms:
        position = lowered.find(term)
        if position >= 0:
            candidate_starts.append(max(0, position - SEARCH_SNIPPET_CHARS // 3))

    if not candidate_starts:
        return clean_text[:SEARCH_SNIPPET_CHARS].rstrip() + "..."

    def match_count(start: int) -> int:
        window = lowered[start:start + SEARCH_SNIPPET_CHARS]
        return sum(window.count(term) for term in query_terms)

    start = max(candidate_starts, key=match_count)
    end = min(len(clean_text), start + SEARCH_SNIPPET_CHARS)
    snippet = clean_text[start:end].strip()
    if start:
        snippet = "..." + snippet
    if end < len(clean_text):
        snippet += "..."
    return snippet


def _format_pages(page_texts: tuple[str, ...], page_numbers: Iterable[int]) -> str:
    sections = []
    for page_number in page_numbers:
        text = page_texts[page_number - 1] or "[No extractable text on this page.]"
        sections.append(f"--- PDF PAGE {page_number} ---\n{text}")
    return "\n\n".join(sections)


def read_pdf_overview(file_path: str) -> str:
    try:
        pages = _load_pdf_pages(file_path)
    except Exception as exc:
        return f"Error reading PDF: {exc}"

    page_count = len(pages)
    if page_count <= SHORT_PDF_PAGE_LIMIT:
        content = _format_pages(pages, range(1, page_count + 1))
        return (
            f"--- START OF PDF CONTENT ({page_count} pages) ---\n"
            f"{content}\n--- END OF PDF CONTENT ---"
        )

    overview_page_count = min(LONG_PDF_OVERVIEW_PAGES, page_count)
    overview = _format_pages(pages, range(1, overview_page_count + 1))
    if len(overview) > LONG_PDF_OVERVIEW_CHARS:
        overview = overview[:LONG_PDF_OVERVIEW_CHARS].rstrip() + "\n[Overview truncated.]"
    return (
        f"--- BOUNDED PDF OVERVIEW ({page_count} pages) ---\n"
        f"This is exact text from pages 1-{overview_page_count}, not a full-paper summary. "
        "Use search_pdf to locate methods, variables, models, and result tables, then "
        "read_pdf_pages to inspect the exact pages before making analytical decisions.\n\n"
        f"{overview}\n--- END BOUNDED PDF OVERVIEW ---"
    )


def search_pdf(file_path: str, query: str, max_results: int = 5) -> str:
    if not query or not query.strip():
        return "Error searching PDF: query must not be empty."
    if not isinstance(max_results, int) or not 1 <= max_results <= MAX_SEARCH_RESULTS:
        return f"Error searching PDF: max_results must be between 1 and {MAX_SEARCH_RESULTS}."

    try:
        pages = _load_pdf_pages(file_path)
    except Exception as exc:
        return f"Error searching PDF: {exc}"

    ranked_pages = _rank_pages(pages, query, max_results=max_results)
    if not ranked_pages:
        return f"No pages matched query '{query}'."

    results = [f"PDF search results for '{query}' ({len(pages)} pages):"]
    for page_number, score in ranked_pages:
        snippet = _best_snippet(pages[page_number - 1], query)
        results.append(f"- page {page_number} | score {score:.2f}\n  {snippet}")
    return "\n".join(results)


def read_pdf_pages(
    file_path: str,
    page_numbers: list[int],
    max_chars: int = MAX_EXACT_CHARS,
) -> str:
    if not isinstance(page_numbers, list) or not page_numbers:
        return "Error reading PDF pages: page_numbers must be a non-empty list."
    if len(page_numbers) > MAX_EXACT_PAGES:
        return f"Error reading PDF pages: request at most {MAX_EXACT_PAGES} pages per call."
    if not isinstance(max_chars, int) or not 1 <= max_chars <= MAX_EXACT_CHARS:
        return f"Error reading PDF pages: max_chars must be between 1 and {MAX_EXACT_CHARS}."

    unique_pages = list(dict.fromkeys(page_numbers))
    if any(not isinstance(page, int) or isinstance(page, bool) for page in unique_pages):
        return "Error reading PDF pages: every page number must be an integer."

    try:
        pages = _load_pdf_pages(file_path)
    except Exception as exc:
        return f"Error reading PDF pages: {exc}"

    invalid_pages = [page for page in unique_pages if page < 1 or page > len(pages)]
    if invalid_pages:
        return (
            f"Error reading PDF pages: invalid page numbers {invalid_pages}; "
            f"the document has {len(pages)} pages."
        )

    content = _format_pages(pages, unique_pages)
    if len(content) > max_chars:
        content = content[:max_chars].rstrip() + "\n[Exact page text truncated at max_chars.]"
    return (
        f"--- EXACT PDF PAGE TEXT ({len(pages)} pages total) ---\n"
        f"{content}\n--- END EXACT PDF PAGE TEXT ---"
    )
