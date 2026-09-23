from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ET

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sources.json"
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "news.json"
MANUAL = DATA_DIR / "manual.json"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_INDEX = ARCHIVE_DIR / "index.json"
SOURCE_HEALTH = DATA_DIR / "source_health.json"

SCHEMA_VERSION = 2
PIPELINE_VERSION = "2.3"
MAX_CURRENT_ITEMS = 240
CURRENT_WINDOW_DAYS = 45
RECENT_ARCHIVE_MONTHS = 4
MIN_HEALTHY_SOURCES_FOR_REBUILD = 4
MAX_RELATED_LINKS = 4
MAX_ITEM_IMAGES = 4
FEATURED_IMAGE_COUNT = 3

FOCUS_CATEGORIES = [
    "Medical Imaging",
    "Medical AI",
    "Trustworthy AI",
    "Foundation Models",
    "AI Agents",
    "AI4Education",
    "AI for Science",
    "Computer Vision",
    "Robotics & Embodied AI",
    "AI Systems & Hardware",
    "AI Policy & Governance",
]

CATEGORY_BASE_RELEVANCE = {
    "Medical Imaging": 100,
    "Medical AI": 96,
    "Trustworthy AI": 96,
    "Foundation Models": 90,
    "AI Agents": 90,
    "AI4Education": 88,
    "AI for Science": 86,
    "Computer Vision": 80,
    "Robotics & Embodied AI": 80,
    "AI Systems & Hardware": 72,
    "AI Policy & Governance": 72,
    "General AI": 58,
}

CONTENT_TYPE_QUALITY = {
    "Regulatory": 100,
    "Government": 96,
    "Journal": 96,
    "Biomedical": 90,
    "Official": 92,
    "Research": 88,
    "Engineering": 78,
    "News": 72,
    "Preprint": 64,
}

SOURCE_TIER_SCORE = {1: 96, 2: 82, 3: 68}

TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "source",
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "using",
    "via", "we", "with", "without", "toward", "towards", "new", "into", "over",
}

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arXiv:\s*)(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
PMID_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")

AI_CORE_RE = re.compile(
    r"\b(artificial intelligence|machine learning|deep learning|neural network|"
    r"large language model|\bllms?\b|foundation model|vision[- ]language|"
    r"multimodal model|generative ai|generative model|transformer|diffusion model|"
    r"ai agent|agentic|autonomous agent|computer vision|reinforcement learning|"
    r"language model|reasoning model|model alignment|ai safety|computer[- ]aided|"
    r"algorithmic model)\b",
    re.I,
)

MEDICAL_CORE_RE = re.compile(
    r"\b(medical|medicine|clinical|patient|healthcare|health care|biomedical|"
    r"radiology|radiological|medical imaging|mri|magnetic resonance|ct scan|"
    r"computed tomography|x[- ]?ray|ultrasound|pathology|oncology|cancer|"
    r"hospital|diagnosis|diagnostic|therapeutic|neuroimaging|brain imaging)\b",
    re.I,
)

CATEGORY_RULES: dict[str, list[tuple[str, float]]] = {
    "Medical Imaging": [
        (r"\bmedical imag(?:e|ing)\b", 8),
        (r"\bradiolog(?:y|ical|ist)\b", 8),
        (r"\bneuroimag(?:e|ing)\b", 8),
        (r"\bcomputed tomography\b|\bct scan\b", 8),
        (r"\bmagnetic resonance\b|\bmri\b", 8),
        (r"\bpet\b|\bpositron emission tomography\b", 7),
        (r"\bultrasound\b|\bsonograph", 7),
        (r"\bx[- ]?ray\b|\bradiograph", 7),
        (r"\bimage reconstruction\b|\btomograph", 7),
        (r"\bmedical image segmentation\b", 7),
        (r"\bpathology image|\bhistopatholog", 6),
    ],
    "Medical AI": [
        (r"\bclinical ai\b|\bmedical ai\b|\bhealthcare ai\b", 8),
        (r"\belectronic health record|\behr\b", 6),
        (r"\bclinical decision support\b", 7),
        (r"\bpatient\b|\bclinical\b|\bhealthcare\b|\bmedicine\b", 3),
        (r"\bbiomedical\b|\bdiagnos(?:is|tic)\b|\bprognos(?:is|tic)\b", 3),
        (r"\bcancer\b|\boncology\b|\bdisease\b|\bhospital\b", 2),
        (r"\bdrug discovery\b|\bclinical trial\b", 4),
    ],
    "Trustworthy AI": [
        (r"\btrustworthy ai\b|\bresponsible ai\b", 9),
        (r"\bai safety\b|\bmodel safety\b|\balignment\b", 8),
        (r"\bhallucination\b|\bhallucinat(?:e|ion|ions)\b", 7),
        (r"\bverifi(?:able|ability|cation)\b|\bprovenance\b|\bauditab", 7),
        (r"\buncertainty quantification\b|\bcalibration\b", 6),
        (r"\brobustness\b|\badversarial\b|\bred[- ]team", 6),
        (r"\bfairness\b|\bbias mitigation\b|\bprivacy\b", 5),
        (r"\binterpretability\b|\bexplainability\b", 5),
        (r"\breproducibility\b|\breliability\b", 4),
        (r"\bmodel evaluation\b|\bevaluation framework\b", 3),
    ],
    "Foundation Models": [
        (r"\bfoundation model", 8),
        (r"\blarge language model|\bllms?\b", 8),
        (r"\bvision[- ]language model|\bvlm\b", 8),
        (r"\bmultimodal (?:model|llm|foundation)", 7),
        (r"\bgenerative ai\b|\bgenerative model", 6),
        (r"\breasoning model\b", 6),
        (r"\btransformer\b", 4),
        (r"\bgpt[- ]?\w*\b|\bclaude\b|\bgemini\b|\bllama\b|\bqwen\b|\bdeepseek\b|\bmistral\b", 6),
    ],
    "AI Agents": [
        (r"\bagentic\b|\bai agent", 9),
        (r"\bautonomous agent|\bmulti[- ]agent", 8),
        (r"\btool[- ]use\b|\btool use\b|\bcomputer use\b", 6),
        (r"\blong[- ]horizon agent|\bagent workflow|\bagentic workflow", 7),
        (r"\bweb agent|\bcoding agent|\bdata agent", 6),
    ],
    "AI4Education": [
        (r"\bai(?:[- ]enabled)? education\b|\bai tutor\b", 9),
        (r"\beducational ai\b|\bintelligent tutoring\b", 8),
        (r"\beducation\b|\beducational\b|\bteaching\b|\bteacher\b", 4),
        (r"\bstudent\b|\bclassroom\b|\btutor\b|\blearning analytics\b", 4),
    ],
    "AI for Science": [
        (r"\bai for science\b|\bscientific discovery\b", 9),
        (r"\bprotein\b|\bmolecule\b|\bmolecular\b|\bchemistry\b", 4),
        (r"\bgenomic|\bbiology\b|\bmaterials science\b", 4),
        (r"\bclimate model|\bweather model|\bphysics\b", 3),
        (r"\bdrug discovery\b", 5),
    ],
    "Robotics & Embodied AI": [
        (r"\bembodied ai\b|\bembodied intelligence\b", 9),
        (r"\brobotics\b|\brobotic\b|\brobot\b", 6),
        (r"\bvision[- ]language[- ]action\b|\bvla\b", 8),
        (r"\bmanipulation\b|\bhumanoid\b|\blocomotion\b", 4),
    ],
    "Computer Vision": [
        (r"\bcomputer vision\b", 8),
        (r"\bobject detection\b|\bimage classification\b", 6),
        (r"\bimage segmentation\b|\bsemantic segmentation\b", 5),
        (r"\bimage generation\b|\bvideo generation\b", 5),
        (r"\b3d vision\b|\bvisual recognition\b|\bvision model\b", 5),
        (r"\bdiffusion model\b", 4),
    ],
    "AI Systems & Hardware": [
        (r"\bai accelerator\b|\bgpu\b|\btpu\b|\bnpu\b", 6),
        (r"\binference server|\binference engine|\bserving\b", 5),
        (r"\btraining efficiency\b|\bquantization\b|\bkernel\b", 4),
        (r"\bcuda\b|\btensorrt\b|\btriton\b|\bcompiler\b", 5),
        (r"\bdata center\b|\bdatacenter\b|\bai chip\b", 4),
    ],
    "AI Policy & Governance": [
        (r"\bai policy\b|\bai governance\b|\bai regulation\b", 9),
        (r"\bregulat(?:ion|ory)\b|\bguidance\b", 4),
        (r"\bexecutive order\b|\blegislat(?:ion|ive)\b", 5),
        (r"\bstandards?\b|\bcompliance\b", 4),
        (r"\bmodel card\b|\btransparency report\b", 4),
    ],
}

TAG_RULES: dict[str, list[str]] = {
    "LLM": [r"\blarge language model|\bllms?\b|\blanguage model\b"],
    "Multimodal": [r"\bmultimodal\b|\bvision[- ]language\b|\bomni[- ]modal\b"],
    "RAG": [r"\bretrieval[- ]augmented\b|\brag\b"],
    "Agents": [r"\bagentic\b|\bai agent|\bautonomous agent|\bmulti[- ]agent"],
    "Safety": [r"\bai safety\b|\balignment\b|\bred[- ]team|\bhallucination\b"],
    "Evaluation": [r"\bbenchmark\b|\bevaluation\b|\bcalibration\b|\bverification\b"],
    "Medical": [r"\bmedical\b|\bclinical\b|\bhealthcare\b|\bbiomedical\b"],
    "Imaging": [r"\bradiolog|\bmedical imag|\bmri\b|\bct scan\b|\bx[- ]?ray\b|\btomograph"],
    "Education": [r"\beducation\b|\bteaching\b|\bstudent\b|\btutor\b"],
    "Robotics": [r"\brobotics\b|\brobotic\b|\bembodied\b|\bhumanoid\b"],
    "Science": [r"\bscientific discovery\b|\bprotein\b|\bmolecule\b|\bchemistry\b|\bgenomic"],
    "Vision": [r"\bcomputer vision\b|\bvisual\b|\bimage\b|\bvideo\b"],
    "Open Source": [r"\bopen[- ]source\b|\bopen weights?\b"],
    "Reasoning": [r"\breasoning\b|\bchain[- ]of[- ]thought\b"],
    "Privacy": [r"\bprivacy\b|\bdifferential privacy\b|\bfederated learning\b"],
    "Hardware": [r"\bgpu\b|\btpu\b|\bnpu\b|\baccelerator\b|\bcuda\b"],
    "Regulation": [r"\bregulat(?:ion|ory)\b|\bguidance\b|\bcompliance\b"],
}

IMPORTANCE_PATTERNS = [
    (r"\bintroduc(?:e|es|ing)\b|\bannounc(?:e|es|ing)\b", 14),
    (r"\breleas(?:e|es|ing)\b|\blaunche?s?\b|\bunveil", 12),
    (r"\bnew model\b|\bmodel family\b|\bfrontier model\b", 12),
    (r"\bbenchmark\b|\bdataset\b|\bevaluation framework\b", 8),
    (r"\bfda\b|\bnih\b|\bnist\b|\bguidance\b|\bregulat", 10),
    (r"\brandomized\b|\bprospective\b|\bmulticenter\b|\bmulti-center\b", 9),
    (r"\bclinical trial\b|\bsystematic review\b|\bmeta-analysis\b", 8),
    (r"\bopen[- ]source\b|\bopen weights?\b", 5),
    (r"\bstate[- ]of[- ]the[- ]art\b|\bsota\b", 3),
]

PROMOTIONAL_PATTERNS = [
    r"\bcustomer story\b",
    r"\bpartnering with\b",
    r"\bwebinar\b",
    r"\bregister now\b",
    r"\bsponsored\b",
    r"\bhow to get started\b",
]

MONTH_NAME_MAP = {
    name.lower(): idx
    for idx, name in enumerate(calendar.month_name)
    if name
}
MONTH_NAME_MAP.update({
    name.lower(): idx
    for idx, name in enumerate(calendar.month_abbr)
    if name
})


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_date(value: datetime | None) -> datetime | None:
    """
    Prevent future issue/publication dates from being interpreted as
    future news events.

    Bibliographic databases may expose a future journal issue date for
    an article that is already indexed online. For freshness ranking
    and archive partitioning, such dates are clamped to collection time.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    value = value.astimezone(timezone.utc)

    now = now_utc()

    if value > now + timedelta(hours=12):
        return now

    return value


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = TAG_RE.sub(" ", text)
    text = text.replace("\u00a0", " ")
    return SPACE_RE.sub(" ", text).strip()


def excerpt(value: Any, limit: int = 390) -> str:
    text = clean_text(value)
    text = re.sub(
        r"^arxiv:\s*\S+\s+announce type:\s*\w+\s+abstract:\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"^(abstract|summary)\s*:\s*", "", text, flags=re.I)
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(" ", 1)[0].strip()
    return shortened + "…"


def iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_struct_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime(
            value.tm_year,
            value.tm_mon,
            value.tm_mday,
            value.tm_hour,
            value.tm_min,
            value.tm_sec,
            tzinfo=timezone.utc,
        )
    except Exception:
        return None


def parse_date_text(value: str) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None

    iso_match = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])-([0-3]\d)\b", text)
    if iso_match:
        try:
            return datetime(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
                tzinfo=timezone.utc,
            )
        except Exception:
            pass

    patterns = [
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b",
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?[,]?\s+(20\d{2})\b",
    ]

    match = re.search(patterns[0], text, flags=re.I)
    if match:
        month_name = match.group(1).lower().replace("sept", "sep")
        month = MONTH_NAME_MAP.get(month_name)
        if month:
            try:
                return datetime(int(match.group(3)), month, int(match.group(2)), tzinfo=timezone.utc)
            except Exception:
                pass

    match = re.search(patterns[1], text, flags=re.I)
    if match:
        month_name = match.group(2).lower().replace("sept", "sep")
        month = MONTH_NAME_MAP.get(month_name)
        if month:
            try:
                return datetime(int(match.group(3)), month, int(match.group(1)), tzinfo=timezone.utc)
            except Exception:
                pass

    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_feed_date(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        dt = parse_struct_time(getattr(entry, attr, None))
        if dt:
            return dt
    for attr in ("published", "updated", "created"):
        dt = parse_date_text(getattr(entry, attr, ""))
        if dt:
            return dt
    return None


def canonical_url(value: str) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = re.sub(r"/+", "/", parsed.path or "/")
        if "arxiv.org" in netloc:
            path = path.replace("/pdf/", "/abs/")
            path = re.sub(r"\.pdf$", "", path)
            path = re.sub(r"v\d+$", "", path)
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_QUERY_KEYS and not k.lower().startswith("utm_")
        ]
        query = urlencode(query_pairs, doseq=True)
        return urlunparse((scheme, netloc, path.rstrip("/") or "/", "", query, ""))
    except Exception:
        return raw


def normalize_title(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"\barxiv:\s*\d{4}\.\d{4,5}(?:v\d+)?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in STOPWORDS]
    return " ".join(tokens)


def title_tokens(value: str) -> set[str]:
    return set(normalize_title(value).split())


def make_id(url: str, title: str, external_id: str = "") -> str:
    seed = external_id or canonical_url(url) or normalize_title(title)
    return hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:20]


def extract_external_ids(url: str, text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    combined = f"{url} {text}"
    arxiv = ARXIV_RE.search(combined)
    if arxiv:
        result["arxiv_id"] = arxiv.group(1)
    pmid = PMID_RE.search(url)
    if pmid:
        result["pmid"] = pmid.group(1)
    doi = DOI_RE.search(combined)
    if doi:
        result["doi"] = doi.group(0).rstrip(".,);]")
    return result


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "WANG-AXIS-AI-Research-Intelligence/2.0 (+https://mkboch.github.io/AI_Website/)"
    })
    return session


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp.replace(path)


def load_sources() -> list[dict[str, Any]]:
    payload = load_json(CONFIG, {})
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise RuntimeError("config/sources.json has no valid sources list")
    return [source for source in sources if source.get("enabled", True)]


def score_category(title: str, summary: str) -> tuple[str, list[str], dict[str, float]]:
    title_text = title.lower()
    summary_text = summary.lower()
    scores: dict[str, float] = {}

    for category, rules in CATEGORY_RULES.items():
        score = 0.0
        for pattern, weight in rules:
            if re.search(pattern, title_text, flags=re.I):
                score += weight * 2.0
            elif re.search(pattern, summary_text, flags=re.I):
                score += weight
        scores[category] = score

    if MEDICAL_CORE_RE.search(f"{title} {summary}"):
        if scores["Medical Imaging"] > 0:
            scores["Medical Imaging"] += 4
        if scores["Medical AI"] > 0:
            scores["Medical AI"] += 3

    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    if not ranked or ranked[0][1] < 3:
        primary = "General AI"
        categories = ["General AI"]
    else:
        primary = ranked[0][0]
        best = ranked[0][1]
        categories = [name for name, value in ranked if value >= max(3, best * 0.48)][:3]
        if primary not in categories:
            categories.insert(0, primary)

    return primary, categories, scores


def derive_tags(title: str, summary: str, primary: str) -> list[str]:
    searchable = f"{title} {summary}"
    tags: list[str] = []
    for tag, patterns in TAG_RULES.items():
        if any(re.search(pattern, searchable, flags=re.I) for pattern in patterns):
            tags.append(tag)
    if primary not in tags:
        tags.insert(0, primary)
    return tags[:7]


def passes_gate(source: dict[str, Any], title: str, summary: str, category: str) -> bool:
    gate = source.get("gate", "none")
    if gate == "none":
        return True
    searchable = f"{title} {summary}"
    has_ai = bool(AI_CORE_RE.search(searchable))
    if gate == "ai":
        return has_ai or category in {
            "Foundation Models", "AI Agents", "Trustworthy AI", "AI4Education",
            "Computer Vision", "Robotics & Embodied AI", "AI Systems & Hardware",
        }
    if gate == "medical_ai":
        return has_ai and bool(MEDICAL_CORE_RE.search(searchable))
    return True


def feed_entry_summary(entry: Any) -> str:
    candidates = [
        getattr(entry, "summary", ""),
        getattr(entry, "description", ""),
    ]
    content = getattr(entry, "content", None)
    if content and isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                candidates.append(item.get("value", ""))
    return max((clean_text(value) for value in candidates), key=len, default="")


def feed_entry_link(entry: Any) -> str:
    link = clean_text(getattr(entry, "link", ""))
    if link:
        return link
    guid = clean_text(getattr(entry, "guid", "") or getattr(entry, "id", ""))
    if guid.startswith("http://") or guid.startswith("https://"):
        return guid
    return ""


def feed_entry_authors(entry: Any) -> list[str]:
    authors: list[str] = []
    raw_authors = getattr(entry, "authors", None)
    if isinstance(raw_authors, list):
        for author in raw_authors:
            if isinstance(author, dict):
                name = clean_text(author.get("name", ""))
            else:
                name = clean_text(author)
            if name and name not in authors:
                authors.append(name)
    author = clean_text(getattr(entry, "author", ""))
    if author and author not in authors:
        authors.append(author)
    return authors[:8]



def normalize_image_url(
    value: Any,
    base_url: str = "",
) -> str:
    raw = html.unescape(
        str(value or "")
    ).strip()

    if not raw:
        return ""

    if raw.startswith(
        (
            "data:",
            "blob:",
        )
    ):
        return ""

    try:
        absolute = urljoin(
            base_url,
            raw,
        )

        parsed = urlparse(
            absolute
        )

        if (
            parsed.scheme.lower()
            not in {
                "http",
                "https",
            }
            or not parsed.netloc
        ):
            return ""

        path_lower = (
            parsed.path
            or ""
        ).lower()

        if re.search(
            r"\.(?:svg|gif)(?:$|\?)",
            path_lower,
        ):
            return ""

        if re.search(
            r"(?:^|[/_.-])"
            r"(?:logo|favicon|avatar|headshot|sprite|emoji|pixel|tracker)"
            r"(?:[/_.-]|$)",
            path_lower,
        ):
            return ""

        query_pairs = [
            (key, val)
            for key, val
            in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if (
                key.lower()
                not in TRACKING_QUERY_KEYS
                and not key.lower().startswith(
                    "utm_"
                )
            )
        ]

        query = urlencode(
            query_pairs,
            doseq=True,
        )

        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc,
                parsed.path,
                "",
                query,
                "",
            )
        )

    except Exception:
        return ""


def normalize_image_urls(
    values: list[Any] | None,
    base_url: str = "",
) -> list[str]:

    output: list[str] = []
    seen: set[str] = set()

    for value in values or []:

        url = normalize_image_url(
            value,
            base_url,
        )

        if not url:
            continue

        key = url.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        output.append(
            url
        )

        if (
            len(output)
            >= MAX_ITEM_IMAGES
        ):
            break

    return output


def image_src_from_tag(
    tag: Any,
) -> str:

    for attr in (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
    ):

        value = clean_text(
            tag.get(
                attr,
                "",
            )
        )

        if value:
            return value

    for attr in (
        "srcset",
        "data-srcset",
    ):

        srcset = clean_text(
            tag.get(
                attr,
                "",
            )
        )

        if not srcset:
            continue

        entries = [
            item.strip()
            for item
            in srcset.split(",")
            if item.strip()
        ]

        if entries:

            return (
                entries[-1]
                .split()[0]
            )

    return ""


def plausible_image_tag(
    tag: Any,
) -> bool:

    width_text = clean_text(
        tag.get(
            "width",
            "",
        )
    )

    height_text = clean_text(
        tag.get(
            "height",
            "",
        )
    )

    width_match = re.search(
        r"\d+",
        width_text,
    )

    height_match = re.search(
        r"\d+",
        height_text,
    )

    if (
        width_match
        and height_match
    ):

        width = int(
            width_match.group()
        )

        height = int(
            height_match.group()
        )

        if (
            width < 240
            or height < 120
        ):
            return False

    return True


def feed_entry_images(
    entry: Any,
    base_url: str,
) -> list[str]:

    candidates: list[Any] = []

    for attr in (
        "media_content",
        "media_thumbnail",
        "enclosures",
        "links",
    ):

        group = getattr(
            entry,
            attr,
            None,
        )

        if not group:
            continue

        if isinstance(
            group,
            dict,
        ):
            group = [group]

        if not isinstance(
            group,
            list,
        ):
            continue

        for value in group:

            if not isinstance(
                value,
                dict,
            ):
                continue

            mime = clean_text(
                value.get(
                    "type",
                    "",
                )
            ).lower()

            if (
                attr
                in {
                    "enclosures",
                    "links",
                }
                and mime
                and not mime.startswith(
                    "image/"
                )
            ):
                continue

            raw = (
                value.get(
                    "url"
                )
                or value.get(
                    "href"
                )
            )

            if raw:
                candidates.append(
                    raw
                )

    html_values: list[str] = []

    for attr in (
        "summary",
        "description",
    ):

        raw = getattr(
            entry,
            attr,
            "",
        )

        if raw:
            html_values.append(
                str(raw)
            )

    content = getattr(
        entry,
        "content",
        None,
    )

    if isinstance(
        content,
        list,
    ):

        for value in content:

            if isinstance(
                value,
                dict,
            ):

                raw = value.get(
                    "value",
                    "",
                )

                if raw:
                    html_values.append(
                        str(raw)
                    )

    for raw_html in html_values:

        try:

            soup = BeautifulSoup(
                raw_html,
                "html.parser",
            )

            for tag in soup.find_all(
                [
                    "img",
                    "source",
                ],
            ):

                raw = image_src_from_tag(
                    tag
                )

                if raw:
                    candidates.append(
                        raw
                    )

        except Exception:
            pass

    return normalize_image_urls(
        candidates,
        base_url,
    )


def closest_images(
    anchor: Any,
    base_url: str,
) -> list[str]:

    candidates: list[Any] = []

    node = anchor

    for _ in range(5):

        if node is None:
            break

        if hasattr(
            node,
            "find_all",
        ):

            for tag in node.find_all(
                [
                    "img",
                    "source",
                ],
                limit=10,
            ):

                if not plausible_image_tag(
                    tag
                ):
                    continue

                raw = image_src_from_tag(
                    tag
                )

                if raw:
                    candidates.append(
                        raw
                    )

        if candidates:
            break

        node = getattr(
            node,
            "parent",
            None,
        )

    return normalize_image_urls(
        candidates,
        base_url,
    )


def extract_article_images(
    session: requests.Session,
    url: str,
) -> list[str]:

    response = session.get(
        url,
        timeout=20,
    )

    response.raise_for_status()

    content_type = (
        response.headers
        .get(
            "content-type",
            "",
        )
        .lower()
    )

    if (
        content_type
        and "html"
        not in content_type
    ):
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    candidates: list[Any] = []

    meta_selectors = [
        (
            "property",
            "og:image",
        ),
        (
            "property",
            "og:image:secure_url",
        ),
        (
            "name",
            "twitter:image",
        ),
        (
            "name",
            "twitter:image:src",
        ),
        (
            "itemprop",
            "image",
        ),
    ]

    for attr, value in meta_selectors:

        for tag in soup.find_all(
            "meta",
            attrs={
                attr: value,
            },
        ):

            raw = tag.get(
                "content",
                "",
            )

            if raw:
                candidates.append(
                    raw
                )

    for tag in soup.find_all(
        "link",
        attrs={
            "rel": "image_src",
        },
    ):

        raw = tag.get(
            "href",
            "",
        )

        if raw:
            candidates.append(
                raw
            )

    content_tags = soup.select(
        "article img, "
        "article source, "
        "main img, "
        "main source, "
        "[role='main'] img, "
        "[role='main'] source"
    )

    if not content_tags:

        content_tags = soup.find_all(
            [
                "img",
                "source",
            ],
            limit=50,
        )

    for tag in content_tags:

        if not plausible_image_tag(
            tag
        ):
            continue

        raw = image_src_from_tag(
            tag
        )

        if raw:
            candidates.append(
                raw
            )

    return normalize_image_urls(
        candidates,
        response.url,
    )


def select_featured_for_enrichment(
    items: list[dict[str, Any]],
    count: int = FEATURED_IMAGE_COUNT,
) -> list[dict[str, Any]]:

    pool = sorted(
        items,
        key=lambda item: float(
            item.get(
                "priority_score",
                0,
            )
            or 0
        ),
        reverse=True,
    )[:60]

    selected: list[dict[str, Any]] = []

    while (
        len(selected) < count
        and pool
    ):

        best_index = 0
        best_score = float(
            "-inf"
        )

        for index, item in enumerate(
            pool
        ):

            score = float(
                item.get(
                    "priority_score",
                    0,
                )
                or 0
            )

            for chosen in selected:

                if (
                    item.get(
                        "source"
                    )
                    == chosen.get(
                        "source"
                    )
                ):
                    score -= 24

                if (
                    item.get(
                        "content_type"
                    )
                    == chosen.get(
                        "content_type"
                    )
                ):
                    score -= 7

                if (
                    item.get(
                        "category"
                    )
                    == chosen.get(
                        "category"
                    )
                ):
                    score -= 6

            if score > best_score:

                best_score = score
                best_index = index

        selected.append(
            pool.pop(
                best_index
            )
        )

    return selected


def enrich_featured_images(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    session = build_session()

    featured = select_featured_for_enrichment(
        items
    )

    for item in featured:

        images = normalize_image_urls(
            item.get(
                "images",
                [],
            ),
            item.get(
                "url",
                "",
            ),
        )

        targets: list[str] = []

        primary_url = clean_text(
            item.get(
                "url",
                "",
            )
        )

        if primary_url:
            targets.append(
                primary_url
            )

        doi = clean_text(
            item.get(
                "doi",
                "",
            )
        )

        if doi:

            doi_url = (
                "https"
                + "://"
                + "doi.org/"
                + doi
            )

            if (
                doi_url
                not in targets
            ):
                targets.append(
                    doi_url
                )

        for related in (
            item.get(
                "related",
                [],
            )
            or []
        ):

            if not isinstance(
                related,
                dict,
            ):
                continue

            related_url = clean_text(
                related.get(
                    "url",
                    "",
                )
            )

            if (
                related_url
                and related_url
                not in targets
            ):
                targets.append(
                    related_url
                )

            if len(
                targets
            ) >= 3:
                break

        for target in targets[:3]:

            if (
                len(images)
                >= MAX_ITEM_IMAGES
            ):
                break

            try:

                extracted = extract_article_images(
                    session,
                    target,
                )

                images = normalize_image_urls(
                    [
                        *images,
                        *extracted,
                    ],
                    target,
                )

            except Exception as error:

                print(
                    "  image enrichment skipped:",
                    item.get(
                        "source",
                        "Unknown",
                    ),
                    clean_text(
                        str(error)
                    )[:160],
                    file=sys.stderr,
                )

        item["images"] = images

        print(
            "  featured images:",
            item.get(
                "source",
                "Unknown",
            ),
            len(images),
            flush=True,
        )

    return items


def make_item(
    source: dict[str, Any],
    title: str,
    url: str,
    summary: str,
    date: datetime | None,
    *,
    authors: list[str] | None = None,
    venue: str = "",
    external_ids: dict[str, str] | None = None,
    publication_status: str = "",
    manual: bool = False,
    images: list[str] | None = None,
) -> dict[str, Any] | None:
    title = clean_text(title)
    url = canonical_url(url)

    # Classification and relevance checks should use the complete
    # available source text. Truncation is only for website display.
    full_summary = clean_text(summary)
    display_summary = excerpt(full_summary)

    date = sanitize_date(date)

    if not title or not url:
        return None

    primary, categories, category_scores = score_category(
        title,
        full_summary,
    )

    if not passes_gate(
        source,
        title,
        full_summary,
        primary,
    ):
        return None

    ids = extract_external_ids(
        url,
        f"{title} {full_summary}",
    )
    if external_ids:
        ids.update({k: clean_text(v) for k, v in external_ids.items() if clean_text(v)})

    external_id = ids.get("doi") or ids.get("arxiv_id") or ids.get("pmid") or ""
    item = {
        "id": make_id(url, title, external_id),
        "title": title,
        "url": url,
        "source": source.get("name", "Unknown source"),
        "source_id": source.get("id", "unknown"),
        "source_class": source.get("source_class", "Other"),
        "source_tier": int(source.get("tier", 3)),
        "content_type": source.get("content_type", "News"),
        "publication_status": publication_status or source.get("content_type", "News"),
        "date": iso(date),
        "category": primary,
        "categories": categories,
        "tags": derive_tags(
            title,
            full_summary,
            primary,
        ),
        "excerpt": display_summary,
        "authors": authors or [],
        "venue": clean_text(venue),
        "manual": bool(manual),
        "related": [],
        "images": normalize_image_urls(
            images or [],
            url,
        ),
        "category_scores": {k: round(v, 2) for k, v in category_scores.items() if v > 0},
    }
    item.update(ids)
    return item


def fetch_rss(session: requests.Session, source: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    response = session.get(source["url"], timeout=35)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    entries = list(feed.entries)[: int(source.get("max_fetch", 60))]
    items: list[dict[str, Any]] = []

    for entry in entries:
        title = clean_text(getattr(entry, "title", ""))
        url = feed_entry_link(entry)
        summary = feed_entry_summary(entry)
        item = make_item(
            source,
            title,
            url,
            summary,
            parse_feed_date(entry),
            authors=feed_entry_authors(entry),
            images=feed_entry_images(
                entry,
                url,
            ),
        )
        if item:
            items.append(item)

    return items, len(entries)


def closest_date_and_summary(anchor: Any) -> tuple[datetime | None, str]:
    candidates = []
    node = anchor
    for _ in range(5):
        if node is None:
            break
        candidates.append(node)
        node = getattr(node, "parent", None)

    for candidate in candidates:
        time_tag = candidate.find("time") if hasattr(candidate, "find") else None
        if time_tag:
            dt = parse_date_text(time_tag.get("datetime", "") or time_tag.get_text(" ", strip=True))
            if dt:
                text = clean_text(candidate.get_text(" ", strip=True))
                return dt, text

    for candidate in candidates:
        text = clean_text(candidate.get_text(" ", strip=True)) if hasattr(candidate, "get_text") else ""
        dt = parse_date_text(text)
        if dt:
            return dt, text

    return None, ""


def fetch_html_links(session: requests.Session, source: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    response = session.get(source["url"], timeout=35)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    pattern = re.compile(source.get("link_regex", ".*"), re.I)
    base = source["url"]
    seen: set[str] = set()
    raw_count = 0
    items: list[dict[str, Any]] = []

    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href", ""))
        parsed_href = urlparse(href)
        path_for_match = parsed_href.path if parsed_href.scheme else href
        if not pattern.search(path_for_match):
            continue
        url = canonical_url(urljoin(base, href))
        if not url or url in seen:
            continue
        seen.add(url)
        raw_count += 1
        title = clean_text(anchor.get_text(" ", strip=True))
        if len(title) < 12:
            continue
        date, context = closest_date_and_summary(anchor)
        if date is None:
            # Avoid resurfacing undated historical links as if they were current.
            continue
        summary = context.replace(title, " ", 1).strip()
        item = make_item(
            source,
            title,
            url,
            summary,
            date,
            images=closest_images(
                anchor,
                base,
            ),
        )
        if item:
            items.append(item)
        if raw_count >= int(source.get("max_fetch", 50)):
            break

    return items, raw_count


def pubmed_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return clean_text("".join(node.itertext()))


def pubmed_date(article: ET.Element) -> datetime | None:
    # Prefer record availability/index dates for freshness ranking.
    # Journal issue dates can legitimately point months into the future.
    paths = [
        ".//PubMedPubDate[@PubStatus='pubmed']",
        ".//PubMedPubDate[@PubStatus='entrez']",
        ".//PubMedPubDate[@PubStatus='medline']",
        ".//Article/ArticleDate",
        ".//Article/Journal/JournalIssue/PubDate",
    ]
    for path in paths:
        node = article.find(path)
        if node is None:
            continue
        year = clean_text(node.findtext("Year", ""))
        month = clean_text(node.findtext("Month", ""))
        day = clean_text(node.findtext("Day", ""))
        medline = clean_text(node.findtext("MedlineDate", ""))
        if not year and medline:
            match = re.search(r"(20\d{2})", medline)
            year = match.group(1) if match else ""
        if not year.isdigit():
            continue
        month_num = 1
        if month:
            if month.isdigit():
                month_num = max(1, min(12, int(month)))
            else:
                month_num = MONTH_NAME_MAP.get(month.lower()[:3], 1)
        day_num = int(day) if day.isdigit() else 1
        try:
            return datetime(int(year), month_num, day_num, tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def fetch_pubmed(session: requests.Session, source: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = source["query"]
    days = int(source.get("days", 10))
    retmax = int(source.get("max_fetch", 60))
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": retmax,
        "sort": "pub date",
        "datetype": "pdat",
        "reldate": days,
    }
    result = session.get(search_url, params=search_params, timeout=35)
    result.raise_for_status()
    ids = result.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return [], 0

    time.sleep(0.35)
    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    fetched = session.get(
        fetch_url,
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        timeout=45,
    )
    fetched.raise_for_status()
    root = ET.fromstring(fetched.content)
    items: list[dict[str, Any]] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = pubmed_text(article.find(".//MedlineCitation/PMID"))
        title = pubmed_text(article.find(".//Article/ArticleTitle"))
        abstract_parts = [pubmed_text(node) for node in article.findall(".//Article/Abstract/AbstractText")]
        summary = " ".join(part for part in abstract_parts if part)
        journal = pubmed_text(article.find(".//Article/Journal/Title"))
        authors: list[str] = []
        for author in article.findall(".//Article/AuthorList/Author"):
            collective = pubmed_text(author.find("CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            fore = pubmed_text(author.find("ForeName"))
            last = pubmed_text(author.find("LastName"))
            name = clean_text(f"{fore} {last}")
            if name:
                authors.append(name)
        doi = ""
        for identifier in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if identifier.attrib.get("IdType", "").lower() == "doi":
                doi = pubmed_text(identifier)
                break
        publication_types = [pubmed_text(node) for node in article.findall(".//Article/PublicationTypeList/PublicationType")]
        status = "Indexed biomedical article"
        if publication_types:
            status = publication_types[0]
        if not pmid:
            continue
        item = make_item(
            source,
            title,
            f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            summary,
            pubmed_date(article),
            authors=authors[:8],
            venue=journal,
            external_ids={"pmid": pmid, "doi": doi},
            publication_status=status,
        )
        if item:
            items.append(item)

    return items, len(ids)


def fetch_source(session: requests.Session, source: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    kind = source.get("kind", "rss")
    if kind == "rss":
        return fetch_rss(session, source)
    if kind == "html_links":
        return fetch_html_links(session, source)
    if kind == "pubmed":
        return fetch_pubmed(session, source)
    raise ValueError(f"Unsupported source kind: {kind}")


def freshness_score(date_value: str) -> float:
    dt = parse_iso(date_value)
    if not dt:
        return 15.0
    days = max(0.0, (now_utc() - dt).total_seconds() / 86400.0)
    if days <= 1:
        return 100.0
    if days <= 3:
        return 94.0
    if days <= 7:
        return 86.0
    if days <= 14:
        return 72.0
    if days <= 30:
        return 56.0
    if days <= 45:
        return 42.0
    if days <= 90:
        return 24.0
    return 8.0


def importance_score(item: dict[str, Any]) -> float:
    text = f"{item.get('title', '')} {item.get('excerpt', '')}"
    score = 38.0
    for pattern, bonus in IMPORTANCE_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            score += bonus
    for pattern in PROMOTIONAL_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            score -= 10
    if item.get("content_type") in {"Regulatory", "Government"}:
        score += 12
    if item.get("content_type") == "Journal":
        score += 8
    if item.get("content_type") == "Preprint":
        score -= 3
    if item.get("manual"):
        score += 15
    return max(0.0, min(100.0, score))


def assign_priority(item: dict[str, Any]) -> dict[str, Any]:
    category = item.get("category", "General AI")
    base_relevance = CATEGORY_BASE_RELEVANCE.get(category, 58)
    category_scores = item.get("category_scores", {}) or {}
    strongest = max(category_scores.values(), default=0.0)
    relevance = min(100.0, base_relevance * 0.82 + min(strongest * 1.6, 18.0))
    source_score = SOURCE_TIER_SCORE.get(int(item.get("source_tier", 3)), 68)
    content_score = CONTENT_TYPE_QUALITY.get(item.get("content_type", "News"), 70)
    freshness = freshness_score(item.get("date", ""))
    importance = importance_score(item)

    priority = (
        relevance * 0.30
        + source_score * 0.18
        + content_score * 0.17
        + freshness * 0.22
        + importance * 0.13
    )
    if item.get("manual"):
        priority += 4
    priority = max(0.0, min(100.0, priority))

    item["relevance_score"] = round(relevance, 1)
    item["freshness_score"] = round(freshness, 1)
    item["priority_score"] = round(priority, 1)
    if priority >= 88:
        item["priority_label"] = "Top signal"
    elif priority >= 80:
        item["priority_label"] = "High relevance"
    elif priority >= 70:
        item["priority_label"] = "Relevant"
    else:
        item["priority_label"] = "Latest"
    return item


def record_quality(item: dict[str, Any]) -> tuple[int, int, int, int]:
    tier = 4 - int(item.get("source_tier", 3))
    type_score = int(CONTENT_TYPE_QUALITY.get(item.get("content_type", "News"), 70))
    excerpt_len = min(len(item.get("excerpt", "")), 500)
    dated = 1 if parse_iso(item.get("date", "")) else 0
    return (tier, type_score, dated, excerpt_len)


def external_keys(item: dict[str, Any]) -> list[str]:
    keys = []
    for field in ("doi", "arxiv_id", "pmid"):
        value = clean_text(item.get(field, "")).lower()
        if value:
            keys.append(f"{field}:{value}")
    return keys


def merge_related(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    related = list(primary.get("related", []) or [])
    candidate = {
        "source": secondary.get("source", ""),
        "url": secondary.get("url", ""),
        "content_type": secondary.get("content_type", ""),
    }
    if candidate["url"] and candidate["url"] != primary.get("url"):
        if all(entry.get("url") != candidate["url"] for entry in related):
            related.append(candidate)
    for entry in secondary.get("related", []) or []:
        if entry.get("url") and entry.get("url") != primary.get("url"):
            if all(existing.get("url") != entry.get("url") for existing in related):
                related.append(entry)
    primary["related"] = related[:MAX_RELATED_LINKS]
    if len(secondary.get("excerpt", "")) > len(primary.get("excerpt", "")):
        primary["excerpt"] = secondary.get("excerpt", "")
    if not primary.get("date") and secondary.get("date"):
        primary["date"] = secondary["date"]
    if not primary.get("venue") and secondary.get("venue"):
        primary["venue"] = secondary["venue"]
    if not primary.get("authors") and secondary.get("authors"):
        primary["authors"] = secondary["authors"]

    primary["images"] = normalize_image_urls(
        [
            *(primary.get("images", []) or []),
            *(secondary.get("images", []) or []),
        ],
        primary.get("url", ""),
    )

    return primary


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exact: dict[str, int] = {}
    title_exact: dict[str, int] = {}
    token_index: dict[str, set[int]] = defaultdict(set)
    output: list[dict[str, Any]] = []

    for raw in sorted(items, key=record_quality, reverse=True):
        item = dict(raw)
        url_key = canonical_url(item.get("url", "")).lower()
        title_key = normalize_title(item.get("title", ""))
        ext_keys = external_keys(item)
        duplicate_idx: int | None = None

        for key in ext_keys:
            if key in exact:
                duplicate_idx = exact[key]
                break
        if duplicate_idx is None and url_key and f"url:{url_key}" in exact:
            duplicate_idx = exact[f"url:{url_key}"]
        if duplicate_idx is None and title_key and title_key in title_exact:
            duplicate_idx = title_exact[title_key]

        tokens = title_tokens(item.get("title", ""))
        if duplicate_idx is None and len(tokens) >= 4:
            longest = sorted(tokens, key=lambda token: (-len(token), token))[:4]
            candidates: set[int] = set()
            for token in longest:
                candidates.update(token_index.get(token, set()))
            for idx in candidates:
                other_tokens = title_tokens(output[idx].get("title", ""))
                union = tokens | other_tokens
                if not union:
                    continue
                jaccard = len(tokens & other_tokens) / len(union)
                if jaccard >= 0.88:
                    duplicate_idx = idx
                    break
                if jaccard >= 0.68:
                    ratio = SequenceMatcher(None, title_key, normalize_title(output[idx].get("title", ""))).ratio()
                    if ratio >= 0.94:
                        duplicate_idx = idx
                        break

        if duplicate_idx is not None:
            primary = output[duplicate_idx]
            if record_quality(item) > record_quality(primary):
                replacement = merge_related(item, primary)
                output[duplicate_idx] = replacement
                primary = replacement
            else:
                merge_related(primary, item)
            for key in external_keys(primary):
                exact[key] = duplicate_idx
            primary_url = canonical_url(primary.get("url", "")).lower()
            if primary_url:
                exact[f"url:{primary_url}"] = duplicate_idx
            title_exact[normalize_title(primary.get("title", ""))] = duplicate_idx
            continue

        idx = len(output)
        output.append(item)
        for key in ext_keys:
            exact[key] = idx
        if url_key:
            exact[f"url:{url_key}"] = idx
        if title_key:
            title_exact[title_key] = idx
        for token in sorted(tokens, key=lambda token: (-len(token), token))[:4]:
            token_index[token].add(idx)

    return output


def normalize_legacy_item(item: dict[str, Any], source_lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title = clean_text(item.get("title", ""))
    url = canonical_url(item.get("url", ""))
    if not title or not url:
        return None

    source_id = item.get("source_id", "")
    source = source_lookup.get(source_id)
    if source is None:
        source_name = clean_text(item.get("source", "Legacy"))
        source = {
            "id": source_id or "legacy",
            "name": source_name or "Legacy",
            "source_class": item.get("source_class", "Legacy"),
            "content_type": item.get("content_type", "News"),
            "tier": int(item.get("source_tier", 3)),
            "gate": "none",
        }

    rebuilt = make_item(
        source,
        title,
        url,
        item.get("excerpt", ""),
        parse_iso(item.get("date", "")),
        authors=item.get("authors", []) if isinstance(item.get("authors"), list) else [],
        venue=item.get("venue", ""),
        external_ids={
            key: item.get(key, "")
            for key in ("doi", "arxiv_id", "pmid")
            if item.get(key)
        },
        publication_status=item.get("publication_status", ""),
        manual=bool(item.get("manual")),
        images=(
            item.get("images", [])
            if isinstance(
                item.get("images"),
                list,
            )
            else []
        ),
    )
    if rebuilt:
        rebuilt["related"] = item.get("related", []) if isinstance(item.get("related"), list) else []
    return rebuilt


def load_manual_items(source_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    manual_payload = load_json(MANUAL, {"items": []})
    candidates = manual_payload.get("items", []) if isinstance(manual_payload, dict) else []
    existing = load_json(OUTPUT, {"items": []})
    if isinstance(existing, dict):
        candidates = list(candidates) + [
            item for item in existing.get("items", []) if isinstance(item, dict) and item.get("manual") is True
        ]

    source = {
        "id": "wang_axis_manual",
        "name": "WANG-AXIS Curated",
        "source_class": "WANG-AXIS",
        "content_type": "Curated",
        "tier": 1,
        "gate": "none",
    }
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        item = make_item(
            source,
            raw.get("title", ""),
            raw.get("url", ""),
            raw.get("excerpt", ""),
            parse_iso(raw.get("date", "")) or now_utc(),
            authors=raw.get("authors", []) if isinstance(raw.get("authors"), list) else [],
            venue=raw.get("venue", ""),
            publication_status=raw.get("publication_status", "Curated"),
            manual=True,
            images=(
                raw.get("images", [])
                if isinstance(
                    raw.get("images"),
                    list,
                )
                else []
            ),
        )
        if item and item["id"] not in seen:
            seen.add(item["id"])
            items.append(item)
    return items


def recent_archive_files(limit: int = RECENT_ARCHIVE_MONTHS) -> list[Path]:
    files = [path for path in ARCHIVE_DIR.glob("????-??.json") if path.name != "index.json"]
    return sorted(files, reverse=True)[:limit]


def load_recent_seed(source_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items: list[dict[str, Any]] = []
    current = load_json(OUTPUT, {"items": []})
    if isinstance(current, dict):
        raw_items.extend(item for item in current.get("items", []) if isinstance(item, dict))
    for path in recent_archive_files():
        payload = load_json(path, {"items": []})
        if isinstance(payload, dict):
            raw_items.extend(item for item in payload.get("items", []) if isinstance(item, dict))

    items: list[dict[str, Any]] = []
    for raw in raw_items:
        normalized = normalize_legacy_item(raw, source_lookup)
        if normalized:
            items.append(normalized)
    return items


def within_current_window(item: dict[str, Any]) -> bool:
    if item.get("manual"):
        return True
    dt = parse_iso(item.get("date", ""))
    if not dt:
        return False
    return dt >= now_utc() - timedelta(days=CURRENT_WINDOW_DAYS)


def select_current(items: list[dict[str, Any]], source_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [assign_priority(dict(item)) for item in items if within_current_window(item)]
    candidates.sort(key=lambda x: (x.get("priority_score", 0), parse_iso(x.get("date", "")) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    source_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    manual = [item for item in candidates if item.get("manual")]
    for item in manual:
        if item["id"] not in selected_ids:
            selected.append(item)
            selected_ids.add(item["id"])
            source_counts[item.get("source_id", "")] += 1
            category_counts[item.get("category", "General AI")] += 1
            type_counts[item.get("content_type", "")] += 1

    # Guarantee representation of each WANG-AXIS focus area when enough material exists.
    for category in FOCUS_CATEGORIES:
        quota = 5
        for item in candidates:
            if len(selected) >= MAX_CURRENT_ITEMS:
                break
            if item["id"] in selected_ids or item.get("category") != category:
                continue
            source_id = item.get("source_id", "")
            max_current = int(source_lookup.get(source_id, {}).get("max_current", 10))
            if source_counts[source_id] >= max_current:
                continue
            selected.append(item)
            selected_ids.add(item["id"])
            source_counts[source_id] += 1
            category_counts[category] += 1
            type_counts[item.get("content_type", "")] += 1
            if category_counts[category] >= quota:
                break

    preprint_cap = int(MAX_CURRENT_ITEMS * 0.32)
    per_category_cap = int(MAX_CURRENT_ITEMS * 0.24)

    for item in candidates:
        if len(selected) >= MAX_CURRENT_ITEMS:
            break
        if item["id"] in selected_ids:
            continue
        source_id = item.get("source_id", "")
        category = item.get("category", "General AI")
        content_type = item.get("content_type", "")
        max_current = int(source_lookup.get(source_id, {}).get("max_current", 10))
        if source_counts[source_id] >= max_current:
            continue
        if category_counts[category] >= per_category_cap:
            continue
        if content_type == "Preprint" and type_counts["Preprint"] >= preprint_cap:
            continue
        selected.append(item)
        selected_ids.add(item["id"])
        source_counts[source_id] += 1
        category_counts[category] += 1
        type_counts[content_type] += 1

    # Relax category limits if needed, but preserve source and preprint balance.
    if len(selected) < MAX_CURRENT_ITEMS:
        relaxed_preprint_cap = int(MAX_CURRENT_ITEMS * 0.38)
        for item in candidates:
            if len(selected) >= MAX_CURRENT_ITEMS:
                break
            if item["id"] in selected_ids:
                continue
            source_id = item.get("source_id", "")
            content_type = item.get("content_type", "")
            max_current = max(2, int(source_lookup.get(source_id, {}).get("max_current", 10)))
            if source_counts[source_id] >= max_current:
                continue
            if content_type == "Preprint" and type_counts["Preprint"] >= relaxed_preprint_cap:
                continue
            selected.append(item)
            selected_ids.add(item["id"])
            source_counts[source_id] += 1
            category_counts[item.get("category", "General AI")] += 1
            type_counts[content_type] += 1

    selected.sort(
        key=lambda x: (x.get("priority_score", 0), parse_iso(x.get("date", "")) or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    for rank, item in enumerate(selected, 1):
        item["rank"] = rank
        item.pop("category_scores", None)
    return selected


def month_key_for_item(item: dict[str, Any]) -> str:
    dt = parse_iso(item.get("date", "")) or now_utc()
    return dt.strftime("%Y-%m")


def remove_future_archive_files() -> None:
    """
    Remove archive partitions whose month lies in the future.

    This repairs archives produced from bibliographic future issue
    dates while preserving those records through the normalized
    current/seed pool.
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    current_month = now_utc().strftime("%Y-%m")

    for candidate in ARCHIVE_DIR.glob("????-??.json"):
        if candidate.stem > current_month:
            print(
                "Removing future archive partition:",
                candidate.name,
                flush=True,
            )
            candidate.unlink(missing_ok=True)


def archive_selected(selected: list[dict[str, Any]]) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in selected:
        grouped[month_key_for_item(item)].append(dict(item))

    for month, new_items in grouped.items():
        path = ARCHIVE_DIR / f"{month}.json"
        existing_payload = load_json(path, {"items": []})
        existing_items = existing_payload.get("items", []) if isinstance(existing_payload, dict) else []
        merged = deduplicate([
            *(item for item in existing_items if isinstance(item, dict)),
            *new_items,
        ])
        merged = [assign_priority(item) for item in merged]
        merged.sort(
            key=lambda x: parse_iso(x.get("date", "")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for item in merged:
            item.pop("category_scores", None)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "month": month,
            "updated_at": iso(now_utc()),
            "item_count": len(merged),
            "items": merged,
        }
        write_json(path, payload)

    build_archive_index()


def build_archive_index() -> dict[str, Any]:
    months = []
    total = 0
    for path in sorted(ARCHIVE_DIR.glob("????-??.json"), reverse=True):
        payload = load_json(path, {})
        count = int(payload.get("item_count", len(payload.get("items", []))) if isinstance(payload, dict) else 0)
        total += count
        months.append({
            "month": path.stem,
            "item_count": count,
            "file": f"data/archive/{path.name}",
        })
    index = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso(now_utc()),
        "total_items": total,
        "months": months,
    }
    write_json(ARCHIVE_INDEX, index)
    return index


def source_summary(health: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(entry.get("status", "unknown") for entry in health)
    classes = Counter(entry.get("source_class", "Other") for entry in health)
    return {
        "total_sources": len(health),
        "healthy_sources": status_counts.get("ok", 0) + status_counts.get("empty", 0),
        "sources_with_items": sum(1 for entry in health if entry.get("accepted", 0) > 0),
        "failed_sources": status_counts.get("error", 0),
        "source_classes": dict(sorted(classes.items())),
    }


def fetch_all_sources(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    session = build_session()
    collected: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []

    for source in sources:
        started = time.monotonic()
        print(f"Fetching {source['name']} ...", flush=True)
        try:
            items, raw_count = fetch_source(session, source)
            collected.extend(items)
            status = "ok" if raw_count > 0 else "empty"
            elapsed = round(time.monotonic() - started, 2)
            health.append({
                "id": source.get("id"),
                "name": source.get("name"),
                "source_class": source.get("source_class"),
                "content_type": source.get("content_type"),
                "tier": source.get("tier"),
                "status": status,
                "fetched": raw_count,
                "accepted": len(items),
                "elapsed_seconds": elapsed,
                "error": "",
            })
            print(f"  fetched={raw_count} accepted={len(items)} status={status} ({elapsed}s)")
        except Exception as error:
            elapsed = round(time.monotonic() - started, 2)
            health.append({
                "id": source.get("id"),
                "name": source.get("name"),
                "source_class": source.get("source_class"),
                "content_type": source.get("content_type"),
                "tier": source.get("tier"),
                "status": "error",
                "fetched": 0,
                "accepted": 0,
                "elapsed_seconds": elapsed,
                "error": clean_text(str(error))[:500],
            })
            print(f"  ERROR: {error}", file=sys.stderr)

    return collected, health


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the WANG-AXIS AI Research Intelligence feed")
    parser.add_argument("--validate-only", action="store_true", help="Fetch sources and write source health without rebuilding the feed")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    sources = load_sources()
    source_lookup = {source["id"]: source for source in sources}
    collected, health = fetch_all_sources(sources)
    health_payload = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "updated_at": iso(now_utc()),
        "summary": source_summary(health),
        "sources": health,
    }
    write_json(SOURCE_HEALTH, health_payload)

    if args.validate_only:
        print(json.dumps(health_payload["summary"], indent=2))
        return 0

    healthy = health_payload["summary"]["healthy_sources"]
    existing_payload = load_json(OUTPUT, {"items": []})
    existing_count = len(existing_payload.get("items", [])) if isinstance(existing_payload, dict) else 0
    if healthy < MIN_HEALTHY_SOURCES_FOR_REBUILD and existing_count >= 20:
        print(
            f"Only {healthy} sources were reachable; preserving existing current feed of {existing_count} items.",
            file=sys.stderr,
        )
        build_archive_index()
        return 0

    manual_items = load_manual_items(source_lookup)
    seed_items = load_recent_seed(source_lookup)
    pool = deduplicate([*manual_items, *seed_items, *collected])
    selected = select_current(pool, source_lookup)

    if selected:
        selected = enrich_featured_images(
            selected
        )

    if not selected and existing_count:
        print("No current items selected; preserving existing feed.", file=sys.stderr)
        return 0

    remove_future_archive_files()

    archive_selected(selected)

    archive_index = load_json(
        ARCHIVE_INDEX,
        {
            "total_items": 0,
            "months": [],
        },
    )

    category_counts = Counter(item.get("category", "General AI") for item in selected)
    type_counts = Counter(item.get("content_type", "Other") for item in selected)
    source_counts = Counter(item.get("source", "Unknown") for item in selected)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "updated_at": iso(now_utc()),
        "methodology": "Balanced, source-tiered, rule-based research intelligence ranking. Priority is not a scientific-quality score.",
        "item_count": len(selected),
        "archive_item_count": int(archive_index.get("total_items", 0)),
        "source_summary": health_payload["summary"],
        "source_health": health,
        "category_counts": dict(category_counts.most_common()),
        "content_type_counts": dict(type_counts.most_common()),
        "source_counts": dict(source_counts.most_common()),
        "items": selected,
    }
    write_json(OUTPUT, payload)

    print()
    print(f"Saved current feed: {len(selected)} items")
    print(f"Archive items: {payload['archive_item_count']}")
    print(f"Configured sources: {len(sources)}")
    print(f"Healthy sources: {healthy}")
    print(f"Failed sources: {health_payload['summary']['failed_sources']}")
    print(f"Preprints in current feed: {type_counts.get('Preprint', 0)} / {len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
