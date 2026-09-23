from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request

from datetime import datetime, timezone
from pathlib import Path

import feedparser


ROOT = Path(__file__).resolve().parents[1]

OUTPUT = ROOT / "data" / "news.json"

MAX_ITEMS = 180


SOURCES = [
    {
        "name": "MIT News - Artificial Intelligence",
        "url": "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
    },
    {
        "name": "Nature - Machine Learning",
        "url": "https://www.nature.com/subjects/machine-learning.rss",
    },
    {
        "name": "arXiv - Artificial Intelligence",
        "url": "https://rss.arxiv.org/rss/cs.AI",
    },
    {
        "name": "arXiv - Computer Vision",
        "url": "https://rss.arxiv.org/rss/cs.CV",
    },
    {
        "name": "arXiv - Computation and Language",
        "url": "https://rss.arxiv.org/rss/cs.CL",
    },
]


CATEGORY_RULES = [
    (
        "Medical Imaging",
        [
            r"\bmedical imag",
            r"\bradiolog",
            r"\bmri\b",
            r"\bmagnetic resonance",
            r"\bx[- ]?ray\b",
            r"\bcomputed tomography\b",
            r"\bct scan\b",
            r"\btomograph",
            r"\bultrasound\b",
            r"\bsonograph",
            r"\bimage reconstruction\b",
            r"\bdiagnostic imag",
            r"\bpatholog",
        ],
    ),
    (
        "Medical AI",
        [
            r"\bmedical\b",
            r"\bmedicine\b",
            r"\bclinical\b",
            r"\bpatient\b",
            r"\bhealth\b",
            r"\bhealthcare\b",
            r"\bbiomedical\b",
            r"\bdisease\b",
            r"\bcancer\b",
            r"\bhospital\b",
            r"\bdrug discovery\b",
        ],
    ),
    (
        "AI4Education",
        [
            r"\beducation\b",
            r"\beducational\b",
            r"\bteaching\b",
            r"\bteacher\b",
            r"\bstudent\b",
            r"\bclassroom\b",
            r"\btutor\b",
        ],
    ),
    (
        "Trustworthy AI",
        [
            r"\btrustworthy\b",
            r"\bai safety\b",
            r"\bsafety\b",
            r"\bverification\b",
            r"\bverifiable\b",
            r"\breliab",
            r"\buncertaint",
            r"\bprovenance\b",
            r"\bhallucination\b",
            r"\bfairness\b",
            r"\bbias\b",
            r"\bprivacy\b",
            r"\bexplainab",
            r"\binterpretab",
            r"\brobustness\b",
        ],
    ),
    (
        "AI Agents",
        [
            r"\bagentic\b",
            r"\bai agent",
            r"\bautonomous agent",
            r"\bmulti[- ]agent",
            r"\btool use\b",
            r"\btool[- ]use\b",
            r"\bcomputer use\b",
        ],
    ),
    (
        "Foundation Models",
        [
            r"\blarge language model",
            r"\bllms?\b",
            r"\bfoundation model",
            r"\bvision[- ]language\b",
            r"\bmultimodal\b",
            r"\bgenerative ai\b",
            r"\bgenerative model",
            r"\btransformer\b",
            r"\bgpt\b",
            r"\bqwen\b",
            r"\bllama\b",
            r"\bdeepseek\b",
        ],
    ),
    (
        "AI for Science",
        [
            r"\bscientific discovery\b",
            r"\bprotein\b",
            r"\bmolecule",
            r"\bchemistry\b",
            r"\bphysics\b",
            r"\bbiology\b",
            r"\bgenomic",
            r"\bmaterials science\b",
            r"\bclimate\b",
        ],
    ),
    (
        "Computer Vision",
        [
            r"\bcomputer vision\b",
            r"\bimage generation\b",
            r"\bimage classification\b",
            r"\bobject detection\b",
            r"\bsegmentation\b",
            r"\bvision model\b",
            r"\bvisual\b",
            r"\bvideo\b",
            r"\bdiffusion model\b",
        ],
    ),
]


TAG_RULES = {
    "LLM": [
        r"\blarge language model",
        r"\bllms?\b",
    ],
    "Multimodal": [
        r"\bmultimodal\b",
        r"\bvision[- ]language\b",
    ],
    "Medical": [
        r"\bmedical\b",
        r"\bclinical\b",
        r"\bhealth\b",
    ],
    "Imaging": [
        r"\bmedical imag",
        r"\bradiolog",
        r"\bmri\b",
        r"\bx[- ]?ray\b",
        r"\btomograph",
    ],
    "Agents": [
        r"\bagentic\b",
        r"\bai agent",
    ],
    "Safety": [
        r"\btrustworthy\b",
        r"\bsafety\b",
        r"\bverification\b",
        r"\breliab",
    ],
    "Vision": [
        r"\bcomputer vision\b",
        r"\bvisual\b",
        r"\bimage\b",
        r"\bvideo\b",
    ],
    "Education": [
        r"\beducation\b",
        r"\bteaching\b",
        r"\bstudent\b",
    ],
}


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    if not value:
        return ""

    value = html.unescape(str(value))

    value = TAG_RE.sub(" ", value)

    value = value.replace("\u00a0", " ")

    value = SPACE_RE.sub(" ", value)

    return value.strip()


def excerpt(value: str | None, limit: int = 330) -> str:
    text = clean_text(value)

    text = re.sub(
        r"^(abstract|summary)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    if len(text) <= limit:
        return text

    shortened = text[:limit].rsplit(" ", 1)[0].strip()

    return shortened + "…"


def parse_date(entry) -> str:
    values = [
        getattr(entry, "published_parsed", None),
        getattr(entry, "updated_parsed", None),
        getattr(entry, "created_parsed", None),
    ]

    for value in values:
        if value:
            try:
                dt = datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                    tzinfo=timezone.utc,
                )

                return dt.isoformat()

            except Exception:
                pass

    return ""


def classify(title: str, summary: str):
    searchable = (title + " " + summary).lower()

    category = "General AI"

    for candidate, patterns in CATEGORY_RULES:
        matched = any(
            re.search(pattern, searchable, flags=re.IGNORECASE)
            for pattern in patterns
        )

        if matched:
            category = candidate
            break

    tags = []

    for tag, patterns in TAG_RULES.items():
        matched = any(
            re.search(pattern, searchable, flags=re.IGNORECASE)
            for pattern in patterns
        )

        if matched:
            tags.append(tag)

    if category not in tags:
        tags.insert(0, category)

    return category, tags[:5]


def canonical_url(value: str) -> str:
    return str(value or "").strip()


def make_id(url: str, title: str) -> str:
    text = (url or title).encode("utf-8", errors="ignore")

    return hashlib.sha256(text).hexdigest()[:18]


def fetch_feed(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "WANG-AXIS-AI-News/1.0"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=35,
    ) as response:
        data = response.read()

    return feedparser.parse(data)


def load_existing():
    if not OUTPUT.exists():
        return {
            "items": []
        }

    try:
        with OUTPUT.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception:
        return {
            "items": []
        }


def date_sort_value(item):
    value = item.get("date", "")

    if not value:
        return 0.0

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).timestamp()

    except Exception:
        return 0.0


def main():
    existing = load_existing()

    manual_items = [
        item
        for item in existing.get("items", [])
        if item.get("manual") is True
    ]

    collected = []

    successful_sources = []
    failed_sources = []

    for source in SOURCES:
        print()
        print("Fetching:", source["name"])

        try:
            feed = fetch_feed(source["url"])

            count = 0

            for entry in feed.entries:
                title = clean_text(
                    getattr(entry, "title", "")
                )

                url = canonical_url(
                    getattr(entry, "link", "")
                )

                summary = clean_text(
                    getattr(
                        entry,
                        "summary",
                        getattr(
                            entry,
                            "description",
                            "",
                        ),
                    )
                )

                if not title or not url:
                    continue

                category, tags = classify(
                    title,
                    summary,
                )

                item = {
                    "id": make_id(url, title),
                    "title": title,
                    "url": url,
                    "source": source["name"],
                    "date": parse_date(entry),
                    "category": category,
                    "tags": tags,
                    "excerpt": excerpt(summary),
                    "manual": False,
                }

                collected.append(item)

                count += 1

            successful_sources.append(
                {
                    "name": source["name"],
                    "count": count,
                }
            )

            print("Accepted:", count)

        except Exception as error:
            failed_sources.append(
                {
                    "name": source["name"],
                    "error": str(error),
                }
            )

            print("FAILED:", error)

    if not successful_sources:
        print()
        print(
            "All feeds failed. Existing data is being preserved."
        )

        return 0

    combined = manual_items + collected

    combined.sort(
        key=date_sort_value,
        reverse=True,
    )

    seen_urls = set()
    seen_titles = set()

    deduplicated = []

    for item in combined:
        url_key = canonical_url(
            item.get("url", "")
        ).lower()

        title_key = re.sub(
            r"[^a-z0-9]+",
            " ",
            item.get("title", "").lower(),
        ).strip()

        if url_key and url_key in seen_urls:
            continue

        if title_key and title_key in seen_titles:
            continue

        if url_key:
            seen_urls.add(url_key)

        if title_key:
            seen_titles.add(title_key)

        deduplicated.append(item)

    manual_final = [
        item
        for item in deduplicated
        if item.get("manual") is True
    ]

    automatic_final = [
        item
        for item in deduplicated
        if item.get("manual") is not True
    ]

    available = max(
        MAX_ITEMS - len(manual_final),
        0,
    )

    final_items = (
        manual_final +
        automatic_final[:available]
    )

    final_items.sort(
        key=date_sort_value,
        reverse=True,
    )

    payload = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "sources_checked": successful_sources,
        "failed_sources": failed_sources,
        "item_count": len(final_items),
        "items": final_items,
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = OUTPUT.with_suffix(
        ".json.tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    temp_path.replace(OUTPUT)

    print()
    print(
        "Saved",
        len(final_items),
        "stories."
    )

    print(
        "Successful sources:",
        len(successful_sources),
    )

    print(
        "Failed sources:",
        len(failed_sources),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())