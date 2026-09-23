from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
NEWS = DATA / "news.json"
HEALTH = DATA / "source_health.json"
ARCHIVE_INDEX = DATA / "archive" / "index.json"
INDEX_HTML = ROOT / "index.html"
APP_JS = ROOT / "app.js"

MIN_CURRENT_ITEMS = 50
MAX_CURRENT_ITEMS = 240
MAX_PREPRINT_SHARE = 0.40
MIN_DISTINCT_SOURCES = 12
MIN_DISTINCT_CATEGORIES = 5
MAX_FUTURE_HOURS = 24


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def load_json(path: Path, errors: list[str]):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        fail(f"{path.relative_to(ROOT)} is not valid JSON: {exc}", errors)
        return {}


def parse_date(value: str):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def validate_news(errors: list[str]) -> None:
    payload = load_json(NEWS, errors)
    if not payload:
        return

    items = payload.get("items")
    if not isinstance(items, list):
        fail("data/news.json: items must be a list", errors)
        return

    declared = payload.get("item_count")
    if declared != len(items):
        fail(f"data/news.json: item_count={declared} but items={len(items)}", errors)

    if not (MIN_CURRENT_ITEMS <= len(items) <= MAX_CURRENT_ITEMS):
        fail(
            f"data/news.json: current item count {len(items)} outside "
            f"{MIN_CURRENT_ITEMS}-{MAX_CURRENT_ITEMS}",
            errors,
        )

    ids = []
    urls = []
    sources = []
    categories = []
    types = []
    now = datetime.now(timezone.utc)

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"data/news.json: item {i} is not an object", errors)
            continue

        item_id = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        source = str(item.get("source", "")).strip()
        category = str(item.get("category", "")).strip()
        content_type = str(item.get("content_type", "")).strip()

        if not item_id:
            fail(f"item {i}: missing id", errors)
        if not title:
            fail(f"item {i}: missing title", errors)
        if not url:
            fail(f"item {i}: missing url", errors)
        else:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                fail(f"item {i}: invalid URL {url}", errors)

        images = item.get(
            "images",
            [],
        )

        if images is None:
            images = []

        if not isinstance(
            images,
            list,
        ):
            fail(
                f"item {i}: images must be a list",
                errors,
            )

        else:

            if len(images) > 4:
                fail(
                    f"item {i}: more than 4 images",
                    errors,
                )

            image_seen = set()

            for image_url in images:

                image_url = str(
                    image_url
                    or ""
                ).strip()

                parsed_image = urlparse(
                    image_url
                )

                if (
                    parsed_image.scheme
                    not in {
                        "http",
                        "https",
                    }
                    or not parsed_image.netloc
                ):
                    fail(
                        f"item {i}: invalid image URL {image_url}",
                        errors,
                    )
                    continue

                image_key = image_url.lower()

                if image_key in image_seen:
                    fail(
                        f"item {i}: duplicate image URL",
                        errors,
                    )

                image_seen.add(
                    image_key
                )

        dt = parse_date(str(item.get("date", "")))
        if dt and (dt - now).total_seconds() > MAX_FUTURE_HOURS * 3600:
            fail(f"item {i}: future date beyond guard: {item.get('date')}", errors)

        ids.append(item_id)
        urls.append(url)
        sources.append(source)
        categories.append(category)
        types.append(content_type)

    duplicate_ids = [k for k, v in Counter(ids).items() if k and v > 1]
    if duplicate_ids:
        fail(f"duplicate item IDs detected: {duplicate_ids[:8]}", errors)

    duplicate_urls = [k for k, v in Counter(urls).items() if k and v > 1]
    if duplicate_urls:
        fail(f"duplicate current-feed URLs detected: {duplicate_urls[:8]}", errors)

    distinct_sources = {s for s in sources if s}
    if len(distinct_sources) < MIN_DISTINCT_SOURCES:
        fail(
            f"only {len(distinct_sources)} distinct contributing sources "
            f"(minimum {MIN_DISTINCT_SOURCES})",
            errors,
        )

    distinct_categories = {c for c in categories if c}
    if len(distinct_categories) < MIN_DISTINCT_CATEGORIES:
        fail(
            f"only {len(distinct_categories)} distinct categories "
            f"(minimum {MIN_DISTINCT_CATEGORIES})",
            errors,
        )

    preprints = sum(1 for t in types if t == "Preprint")
    preprint_share = preprints / max(1, len(items))
    if preprint_share > MAX_PREPRINT_SHARE:
        fail(
            f"preprint share {preprint_share:.1%} exceeds "
            f"{MAX_PREPRINT_SHARE:.0%}",
            errors,
        )

    source_counts = Counter(sources)
    if source_counts:
        name, count = source_counts.most_common(1)[0]
        allowed = max(25, int(len(items) * 0.15) + 1)
        if count > allowed:
            fail(
                f"single-source concentration too high: {name}={count}, "
                f"allowed <= {allowed}",
                errors,
            )

    summary = payload.get("source_summary") or {}
    health = payload.get("source_health")
    if not isinstance(health, list):
        fail("data/news.json: source_health must be a list", errors)
    else:
        total = int(summary.get("total_sources", -1))
        if total != len(health):
            fail(
                f"source_summary.total_sources={total} but "
                f"source_health has {len(health)} entries",
                errors,
            )

        actual_failed = sum(1 for x in health if x.get("status") == "error")
        if int(summary.get("failed_sources", -1)) != actual_failed:
            fail("source_summary.failed_sources does not match source_health", errors)


def validate_health(errors: list[str]) -> None:
    payload = load_json(HEALTH, errors)
    if not payload:
        return
    sources = payload.get("sources")
    if not isinstance(sources, list):
        fail("data/source_health.json: sources must be a list", errors)
        return

    names = [str(x.get("id", "")).strip() for x in sources if isinstance(x, dict)]
    duplicate_ids = [k for k, v in Counter(names).items() if k and v > 1]
    if duplicate_ids:
        fail(f"duplicate source-health IDs: {duplicate_ids}", errors)


def validate_archive(errors: list[str]) -> None:
    payload = load_json(ARCHIVE_INDEX, errors)
    if not payload:
        return

    months = payload.get("months")
    if not isinstance(months, list):
        fail("archive index: months must be a list", errors)
        return

    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    total = 0

    for entry in months:
        month = str(entry.get("month", ""))
        rel = str(entry.get("file", ""))
        declared = int(entry.get("item_count", 0))

        if month > current_month:
            fail(f"future archive partition present: {month}", errors)

        path = ROOT / rel
        if not path.exists():
            fail(f"archive index references missing file: {rel}", errors)
            continue

        month_payload = load_json(path, errors)
        items = month_payload.get("items", [])
        if not isinstance(items, list):
            fail(f"{rel}: items must be a list", errors)
            continue

        if declared != len(items):
            fail(
                f"{rel}: index says {declared} items but file has {len(items)}",
                errors,
            )
        total += len(items)

    declared_total = int(payload.get("total_items", -1))
    if declared_total != total:
        fail(
            f"archive total_items={declared_total} but monthly files sum to {total}",
            errors,
        )


def validate_interface(errors: list[str]) -> None:
    try:
        html = INDEX_HTML.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
    except Exception as exc:
        fail(f"could not read static interface files: {exc}", errors)
        return

    ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', html))
    required = set(re.findall(r'\bel\(["\']([^"\']+)["\']\)', js))

    missing = sorted(required - ids)
    if missing:
        fail(f"app.js references missing HTML IDs: {missing}", errors)

    if 'id="methodology"' in html or 'href="#methodology"' in html:
        fail("removed Methodology public section unexpectedly reappeared", errors)


def main() -> int:
    errors: list[str] = []

    validate_news(errors)
    validate_health(errors)
    validate_archive(errors)
    validate_interface(errors)

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f" - {error}")
        return 1

    news = load_json(NEWS, [])
    items = news.get("items", []) if isinstance(news, dict) else []
    sources = len({x.get("source") for x in items if isinstance(x, dict)})
    categories = len({x.get("category") for x in items if isinstance(x, dict)})
    preprints = sum(
        1 for x in items
        if isinstance(x, dict) and x.get("content_type") == "Preprint"
    )

    print("VALIDATION OK")
    print(f" current_items={len(items)}")
    print(f" contributing_sources={sources}")
    print(f" categories={categories}")
    print(f" preprint_share={preprints / max(1, len(items)):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
