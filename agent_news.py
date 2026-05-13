from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import dataclasses
import datetime as dt
import email.utils
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


AGENT_NAME = "Agent News"


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def writable_base_dir() -> Path:
    preferred = runtime_base_dir()
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".agent_news_write_test"
        probe.write_text("ok", encoding="utf-8")
        with contextlib.suppress(OSError):
            probe.unlink(missing_ok=True)
        return preferred
    except OSError:
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Agent News"
        with contextlib.suppress(OSError):
            local.mkdir(parents=True, exist_ok=True)
            return local
        return preferred


BASE_DIR = writable_base_dir()
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
PROFILE_PATH = BASE_DIR / "interest_profile.json"
LATEST_PATH = OUTPUT_DIR / "agent_news_latest.html"

HTTP_TIMEOUT_SECONDS = 12
MAX_WORKERS = 10
ITEMS_PER_THEME = 4
REPORT_ITEMS = 44
PROFILE_VERSION = 3
THEME_COUNT = 11
QUERIES_PER_THEME = 4
SCHEDULE_TIME_LABEL = "08:30"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) AgentNews/1.0"
)


STOPWORDS = {
    "about",
    "abril",
    "after",
    "ahora",
    "also",
    "ante",
    "antes",
    "because",
    "cada",
    "como",
    "cuando",
    "desde",
    "dice",
    "donde",
    "este",
    "esta",
    "estos",
    "estas",
    "para",
    "pero",
    "sobre",
    "that",
    "the",
    "this",
    "tras",
    "with",
    "your",
}


NOISE_TOKENS = STOPWORDS | {
    "account",
    "aerialview",
    "agent",
    "agentnews",
    "allitems",
    "archivo",
    "archivos",
    "appdata",
    "aspx",
    "cache",
    "chat",
    "chrome",
    "cliente",
    "clientes",
    "colab",
    "contreras",
    "copia",
    "dashboard",
    "default",
    "desktop",
    "documentos",
    "documents",
    "drive",
    "download",
    "downloads",
    "edge",
    "envio",
    "file",
    "files",
    "fijos",
    "forms",
    "campaign",
    "gclid",
    "gratis",
    "google",
    "history",
    "html",
    "http",
    "https",
    "ipynb",
    "imagen",
    "imagenes",
    "infobae",
    "jpeg",
    "jpg",
    "listado",
    "listados",
    "local",
    "login",
    "landxml",
    "microsoft",
    "news",
    "noticias",
    "onedrive",
    "personal",
    "planis",
    "output",
    "profile",
    "puntos",
    "sites",
    "teams",
    "search",
    "silenciosa",
    "source",
    "temp",
    "tramo",
    "todos",
    "transformar",
    "user",
    "users",
    "vmos",
    "vmoslcall",
    "viewid",
    "windows",
    "www",
    "xlsx",
    "xls",
    "docx",
    "pptx",
    "pdf",
    "png",
    "youtube",
}

THEME_COLORS = [
    "#1b6aa8",
    "#a4551f",
    "#3155a4",
    "#3b7b55",
    "#6a4ca3",
    "#9b3b52",
    "#57713b",
    "#46666f",
    "#b04332",
    "#84611f",
    "#236b77",
]

GENERIC_FALLBACK_KEYWORDS = [
    ["tecnologia", "innovacion", "software"],
    ["economia", "mercados", "empresas"],
    ["ciencia", "salud", "investigacion"],
    ["cultura", "entretenimiento", "tendencias"],
    ["mundo", "politica", "sociedad"],
]

FIXED_THEME_DEFINITIONS = [
    {
        "name": "Argentina",
        "keywords": ["argentina", "politica", "economia", "sociedad"],
        "queries": [
            "Argentina noticias hoy politica economia",
            "Argentina actualidad ultimas noticias",
            "Argentina economia mercados empresas noticias",
            "Argentina sociedad gobierno novedades",
        ],
    },
    {
        "name": "Petroleo",
        "keywords": ["petroleo", "energia", "vaca muerta", "brent", "wti"],
        "queries": [
            "petroleo Argentina Vaca Muerta noticias hoy",
            "precio petroleo Brent WTI noticias hoy",
            "industria petrolera energia novedades",
            "oil market news today",
        ],
    },
    {
        "name": "Gas",
        "keywords": ["gas", "gas natural", "gnl", "vaca muerta", "energia"],
        "queries": [
            "gas natural Argentina Vaca Muerta noticias hoy",
            "GNL gas natural energia noticias",
            "gasoducto Argentina energia novedades",
            "natural gas market news today",
        ],
    },
    {
        "name": "Litio",
        "keywords": ["litio", "mineria", "baterias", "energia"],
        "queries": [
            "litio Argentina mineria noticias hoy",
            "litio baterias energia novedades",
            "precio litio mercado noticias hoy",
            "lithium market news today",
        ],
    },
    {
        "name": "Drones",
        "keywords": ["drones", "uav", "topografia", "agricultura", "inspeccion"],
        "queries": [
            "drones industria tecnologia noticias hoy",
            "drones topografia agricultura inspeccion novedades",
            "UAV drones novedades tendencias",
            "drone technology news today",
        ],
    },
    {
        "name": "Equipamiento Topografico",
        "keywords": ["equipamiento topografico", "gnss", "rtk", "lidar", "estacion total"],
        "queries": [
            "equipamiento topografico noticias novedades",
            "GNSS GPS RTK topografia noticias",
            "estaciones totales scanners laser LiDAR novedades",
            "surveying equipment news today",
        ],
    },
    {
        "name": "Software SAAS",
        "keywords": ["software", "saas", "cloud", "startups", "enterprise"],
        "queries": [
            "software SaaS empresas noticias hoy",
            "SaaS startups producto tecnologia novedades",
            "software enterprise cloud noticias hoy",
            "SaaS news today",
        ],
    },
    {
        "name": "Inteligencia artificial",
        "keywords": ["inteligencia artificial", "ia", "ai", "generativa", "modelos"],
        "queries": [
            "inteligencia artificial noticias hoy",
            "IA generativa empresas tecnologia novedades",
            "modelos AI OpenAI Google Anthropic noticias",
            "artificial intelligence news today",
        ],
    },
    {
        "name": "Novedades Tech",
        "keywords": ["tech", "tecnologia", "innovacion", "startups", "big tech"],
        "queries": [
            "novedades tech tecnologia noticias hoy",
            "startups tecnologia innovacion noticias",
            "big tech software hardware novedades",
            "technology news today",
        ],
    },
    {
        "name": "Ultimos Gadgets",
        "keywords": ["gadgets", "smartphones", "wearables", "dispositivos"],
        "queries": [
            "ultimos gadgets tecnologia noticias hoy",
            "smartphones wearables gadgets novedades",
            "lanzamientos dispositivos tecnologia noticias",
            "new gadgets news today",
        ],
    },
    {
        "name": "Robots",
        "keywords": ["robots", "robotica", "automatizacion", "humanoides"],
        "queries": [
            "robots robotica noticias hoy",
            "robots humanoides automatizacion novedades",
            "robotica industrial IA noticias",
            "robotics news today",
        ],
    },
]


@dataclasses.dataclass
class Article:
    category: str
    query: str
    title: str
    link: str
    source: str
    description: str
    published: dt.datetime | None
    image_url: str = ""
    score: float = 0.0

    @property
    def key(self) -> str:
        return normalize_for_key(self.title)


@dataclasses.dataclass
class Theme:
    name: str
    target: int
    accent: str
    queries: list[str]
    keywords: list[str]
    evidence_count: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_dirs()
    timestamp = now_local().strftime("%Y-%m-%d %H:%M:%S")
    with (LOG_DIR / "agent_news.log").open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")


def strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return value.encode("ascii", "ignore").decode("ascii")


def compact_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\xa0", " ")
    return compact_spaces(value)


def normalize_for_key(value: str) -> str:
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [t for t in value.split() if t not in STOPWORDS]
    return " ".join(tokens[:16])


def shorten_chars(value: str, limit: int) -> str:
    value = compact_spaces(value)
    if len(value) <= limit:
        return value
    cut = value[: max(0, limit - 1)].rstrip()
    last_break = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(", "))
    if last_break >= int(limit * 0.55):
        cut = cut[: last_break + 1]
    else:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".;, ") + "..."


def rss_url(query: str) -> str:
    query_with_window = f"{query} when:1d"
    params = {
        "q": query_with_window,
        "hl": "es-419",
        "gl": "AR",
        "ceid": "AR:es-419",
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def parse_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    with contextlib.suppress(Exception):
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone()
    return None


def xml_text(parent: ET.Element, child_name: str) -> str:
    found = parent.find(child_name)
    return clean_text(found.text if found is not None and found.text else "")


def find_source(item: ET.Element) -> str:
    found = item.find("source")
    if found is not None and found.text:
        return clean_text(found.text)
    return ""


def find_image(item: ET.Element) -> str:
    for child in item.iter():
        tag = child.tag.lower()
        if tag.endswith("content") or tag.endswith("thumbnail"):
            url = child.attrib.get("url", "")
            if url.startswith("http"):
                return url
    return ""


def clean_title(title: str, source: str) -> str:
    title = clean_text(title)
    if source:
        suffix = f" - {source}"
        if title.lower().endswith(suffix.lower()):
            title = title[: -len(suffix)].strip()
    return title


def fetch_feed(category: str, query: str) -> list[Article]:
    url = rss_url(query)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        data = response.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall("./channel/item"):
        source = find_source(item)
        title = clean_title(xml_text(item, "title"), source)
        link = xml_text(item, "link")
        description = clean_text(xml_text(item, "description"))
        published = parse_date(xml_text(item, "pubDate"))
        if not title or not link:
            continue
        items.append(
            Article(
                category=category,
                query=query,
                title=title,
                link=link,
                source=source,
                description=description,
                published=published,
                image_url=find_image(item),
            )
        )
    return items


def discover_history_paths() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    appdata = Path(os.environ.get("APPDATA", ""))
    candidates = []
    chromium_roots = [
        local / "Google" / "Chrome" / "User Data",
        local / "Microsoft" / "Edge" / "User Data",
        local / "BraveSoftware" / "Brave-Browser" / "User Data",
        local / "Chromium" / "User Data",
    ]
    for root in chromium_roots:
        if not root.exists():
            continue
        for profile in root.iterdir():
            if profile.is_dir() and (profile.name == "Default" or profile.name.startswith("Profile")):
                history = profile / "History"
                if history.exists():
                    candidates.append(history)

    firefox_profiles = appdata / "Mozilla" / "Firefox" / "Profiles"
    if firefox_profiles.exists():
        for profile in firefox_profiles.iterdir():
            places = profile / "places.sqlite"
            if places.exists():
                candidates.append(places)
    return candidates


def chrome_cutoff(days: int = 45) -> int:
    epoch = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return int((cutoff - epoch).total_seconds() * 1_000_000)


def read_sqlite_rows(path: Path, query: str, params: tuple = ()) -> list[tuple]:
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return []
    try:
        cur = conn.execute(query, params)
        return list(cur.fetchall())
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def read_browser_history_records(limit_per_db: int = 600) -> list[str]:
    records: list[str] = []
    for path in discover_history_paths():
        name = path.name.lower()
        if name == "history":
            rows = read_sqlite_rows(
                path,
                """
                SELECT title, url
                FROM urls
                WHERE last_visit_time >= ?
                ORDER BY last_visit_time DESC
                LIMIT ?
                """,
                (chrome_cutoff(), limit_per_db),
            )
        elif name == "places.sqlite":
            rows = read_sqlite_rows(
                path,
                """
                SELECT title, url
                FROM moz_places
                WHERE last_visit_date IS NOT NULL
                ORDER BY last_visit_date DESC
                LIMIT ?
                """,
                (limit_per_db,),
            )
        else:
            rows = []
        for title, url in rows:
            path_words = ""
            with contextlib.suppress(Exception):
                parsed = urllib.parse.urlparse(url or "")
                path_words = f"{parsed.path} {parsed.query}"
            record = compact_spaces(f"{title or ''} {path_words}")
            if record:
                records.append(record)
    return records


def tokenize_for_profile(value: str) -> list[str]:
    value = strip_accents(value).lower()
    value = re.sub(r"https?://", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return [t for t in value.split() if is_useful_token(t)]


def is_useful_token(token: str) -> bool:
    allowed_short = {"qgis", "gdal", "gps"}
    if len(token) < 4 or len(token) > 28:
        return False
    if len(token) == 4 and token not in allowed_short:
        return False
    if any(char.isdigit() for char in token):
        return False
    if re.search(r"(.)\1{2,}", token):
        return False
    if token in NOISE_TOKENS:
        return False
    if token.isdigit():
        return False
    if re.fullmatch(r"[a-f0-9]{10,}", token):
        return False
    if re.fullmatch(r"\d+[a-z]{0,3}", token):
        return False
    return True


def scan_tree_records(root: Path, max_items: int = 3000) -> list[str]:
    records: list[str] = []
    count = 0
    ignored = {
        ".git",
        "__pycache__",
        ".tool_cache",
        ".jupyter_runtime",
        ".matplotlib_cache",
        "AppData",
        "node_modules",
        "OneDriveTemp",
    }
    if not root.exists():
        return records
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignored]
        folder_name = Path(current).name
        for name in dirs + files:
            record = compact_spaces(f"{folder_name} {name}")
            if record:
                records.append(record)
            count += 1
            if count >= max_items:
                return records
    return records


def personal_scan_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
    ]
    roots.extend(path for path in home.glob("OneDrive*") if path.is_dir())
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def collect_profile_records() -> tuple[list[str], dict]:
    file_records: list[str] = []
    roots = personal_scan_roots()
    for root in roots:
        file_records.extend(scan_tree_records(root, max_items=1200))
    history_records = read_browser_history_records()
    stats = {
        "file_records": len(file_records),
        "history_records": len(history_records),
        "scan_roots": [str(root) for root in roots],
    }
    return history_records + file_records, stats


def build_record_counters(records: list[str]) -> tuple[Counter, Counter, list[set[str]]]:
    term_count: Counter = Counter()
    doc_count: Counter = Counter()
    record_sets: list[set[str]] = []
    for record in records:
        tokens = tokenize_for_profile(record)
        if not tokens:
            continue
        term_count.update(tokens)
        token_set = set(tokens)
        doc_count.update(token_set)
        record_sets.append(token_set)
    return term_count, doc_count, record_sets


def term_score(term: str, term_count: Counter, doc_count: Counter) -> float:
    return float(term_count[term]) + float(doc_count[term] * 2)


def display_term(term: str) -> str:
    known = {
        "autocad": "AutoCAD",
        "civil3d": "Civil 3D",
        "excel": "Excel",
        "openai": "OpenAI",
        "python": "Python",
        "qgis": "QGIS",
        "youtube": "YouTube",
    }
    return known.get(term, term.replace("_", " ").title())


def make_theme_name(keywords: list[str]) -> str:
    visible = [display_term(term) for term in keywords[:3]]
    return " / ".join(visible)


def make_theme_queries(keywords: list[str]) -> list[str]:
    primary = " ".join(keywords[:3])
    seed = keywords[0]
    secondary = " ".join(keywords[:2]) if len(keywords) > 1 else seed
    queries = [
        f"{primary} noticias hoy",
        f"{primary} actualidad ultimas noticias",
        f"{secondary} novedades tendencias",
        f"{seed} news today",
    ]
    return queries[:QUERIES_PER_THEME]


def normalize_theme_targets(themes: list[Theme]) -> list[Theme]:
    if not themes:
        return themes
    for theme in themes:
        theme.target = ITEMS_PER_THEME
    return themes


def build_fixed_themes() -> list[Theme]:
    themes: list[Theme] = []
    for index, item in enumerate(FIXED_THEME_DEFINITIONS):
        themes.append(
            Theme(
                name=item["name"],
                target=ITEMS_PER_THEME,
                accent=THEME_COLORS[index % len(THEME_COLORS)],
                queries=item["queries"][:QUERIES_PER_THEME],
                keywords=item["keywords"],
                evidence_count=0,
            )
        )
    return themes


def fallback_themes() -> list[Theme]:
    return build_fixed_themes()


def build_dynamic_themes(records: list[str]) -> list[Theme]:
    term_count, doc_count, record_sets = build_record_counters(records)
    candidates = [
        term
        for term in term_count
        if doc_count[term] >= 2 or term_count[term] >= 4
    ]
    candidates.sort(key=lambda term: term_score(term, term_count, doc_count), reverse=True)

    themes: list[Theme] = []
    used_terms: set[str] = set()
    for seed in candidates:
        if seed in used_terms:
            continue

        related_counter: Counter = Counter()
        evidence = 0
        for token_set in record_sets:
            if seed not in token_set:
                continue
            evidence += 1
            related_counter.update(token for token in token_set if token != seed and token not in used_terms)

        related = [
            term
            for term, _ in related_counter.most_common(6)
            if is_useful_token(term) and term != seed
        ]
        keywords = [seed] + related[:2]
        if len(keywords) < 2 and evidence < 3:
            continue

        themes.append(
            Theme(
                name=make_theme_name(keywords),
                target=0,
                accent=THEME_COLORS[len(themes) % len(THEME_COLORS)],
                queries=make_theme_queries(keywords),
                keywords=keywords,
                evidence_count=evidence,
            )
        )
        used_terms.update(keywords)
        if len(themes) >= THEME_COUNT:
            break

    if len(themes) < 3:
        themes.extend(fallback_themes()[len(themes):])
    return normalize_theme_targets(themes[:THEME_COUNT])


def profile_themes(profile: dict) -> list[dict]:
    themes = profile.get("themes")
    if isinstance(themes, list) and themes:
        return themes
    return [theme.to_dict() for theme in fallback_themes()]


def build_interest_profile() -> dict:
    themes = build_fixed_themes()
    boost_terms = sorted({term for theme in themes for term in theme.keywords[:3]})

    return {
        "agent": AGENT_NAME,
        "profile_version": PROFILE_VERSION,
        "profile_mode": "fixed_topics",
        "generated_at": now_local().isoformat(timespec="seconds"),
        "privacy": (
            "Perfil manual: usa solo las tematicas configuradas en el agente. "
            "No escanea archivos, historial, cookies, passwords ni sesiones."
        ),
        "scan_stats": {"mode": "fixed_topics"},
        "detected_interests": [theme.name for theme in themes],
        "boost_terms": boost_terms,
        "themes": [theme.to_dict() for theme in themes],
    }


def save_profile(profile: dict) -> None:
    ensure_dirs()
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def load_or_create_profile(force: bool = False) -> dict:
    if PROFILE_PATH.exists() and not force:
        with contextlib.suppress(Exception):
            profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if (
                profile.get("profile_version") == PROFILE_VERSION
                and profile.get("profile_mode") == "fixed_topics"
                and profile.get("themes")
            ):
                return profile
    profile = build_interest_profile()
    save_profile(profile)
    return profile


def score_article(article: Article, profile: dict) -> float:
    text = strip_accents(f"{article.title} {article.description} {article.source}").lower()
    score = 1.0

    if article.published:
        age_hours = max(0.0, (now_local() - article.published).total_seconds() / 3600.0)
        score += max(0.0, 30.0 - age_hours) / 6.0

    theme = next((item for item in profile_themes(profile) if item.get("name") == article.category), None)
    if theme:
        for keyword in theme.get("keywords", []):
            if strip_accents(keyword).lower() in text:
                score += 2.0

    for term in profile.get("boost_terms", []):
        if strip_accents(term).lower() in text:
            score += 1.2

    if article.source:
        score += 0.4
    if len(article.description) > 80:
        score += 0.3
    return score


def collect_articles(profile: dict) -> tuple[list[Article], list[str]]:
    jobs = []
    errors: list[str] = []
    for theme in profile_themes(profile):
        for query in theme.get("queries", []):
            jobs.append((theme.get("name", "Tema"), query))

    collected: list[Article] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_job = {executor.submit(fetch_feed, category, query): (category, query) for category, query in jobs}
        for future in concurrent.futures.as_completed(future_to_job):
            category, query = future_to_job[future]
            try:
                articles = future.result()
            except Exception as exc:  # RSS failures should not stop the morning report.
                errors.append(f"{category}: {query} ({exc})")
                continue
            for article in articles:
                article.score = score_article(article, profile)
            collected.extend(articles)
    return collected, errors


def choose_articles(articles: list[Article], profile: dict) -> list[Article]:
    themes = profile_themes(profile)
    by_category: dict[str, list[Article]] = {theme.get("name", "Tema"): [] for theme in themes}
    global_seen: set[str] = set()

    for article in sorted(articles, key=lambda item: item.score, reverse=True):
        key = article.key
        if not key or key in global_seen:
            continue
        global_seen.add(key)
        if article.category in by_category:
            by_category[article.category].append(article)

    selected: list[Article] = []
    for theme in themes:
        name = theme.get("name", "Tema")
        target = int(theme.get("target", ITEMS_PER_THEME))
        selected.extend(by_category.get(name, [])[:target])

    return selected


def fallback_articles(profile: dict) -> list[Article]:
    today = now_local()
    topics: list[tuple[str, str]] = []
    for theme in profile_themes(profile):
        name = theme.get("name", "Tema")
        target = int(theme.get("target", ITEMS_PER_THEME))
        for index in range(target):
            topics.append((name, f"{name}: noticia pendiente {index + 1}"))
    return [
        Article(
            category=category,
            query=topic,
            title=topic,
            link="",
            source="Sin conexion",
            description="No se pudo obtener una noticia verificable para esta tematica en esta ejecucion. El agente dejo este espacio como recordatorio de busqueda.",
            published=today,
            score=0.0,
        )
        for category, topic in topics
    ]


def target_total(profile: dict) -> int:
    return sum(int(theme.get("target", ITEMS_PER_THEME)) for theme in profile_themes(profile))


def complete_article_targets(articles: list[Article], profile: dict) -> list[Article]:
    themes = profile_themes(profile)
    targets = {theme.get("name", "Tema"): int(theme.get("target", ITEMS_PER_THEME)) for theme in themes}
    selected: list[Article] = []
    selected_keys: set[str] = set()
    counts: Counter = Counter()

    for theme in themes:
        name = theme.get("name", "Tema")
        target = targets[name]
        for article in articles:
            if article.category != name or counts[name] >= target:
                continue
            if article.key in selected_keys:
                continue
            selected.append(article)
            selected_keys.add(article.key)
            counts[name] += 1

    for fallback in fallback_articles(profile):
        name = fallback.category
        if counts[name] >= targets.get(name, ITEMS_PER_THEME):
            continue
        if fallback.key in selected_keys:
            continue
        selected.append(fallback)
        selected_keys.add(fallback.key)
        counts[name] += 1

    return selected


def make_summary(article: Article) -> str:
    source = f" Fuente: {article.source}." if article.source else ""
    description = article.description
    title = article.title
    if description.lower().startswith(title.lower()[: max(20, min(80, len(title)))]):
        text = description
    else:
        text = f"{title}. {description}"
    text = compact_spaces(text)
    if source and source.lower() not in text.lower()[-80:]:
        text = compact_spaces(text + source)
    return shorten_chars(text, 300)


def format_date(value: dt.datetime | None) -> str:
    if not value:
        return "Sin fecha"
    return value.strftime("%d/%m/%Y %H:%M")


def grouped(articles: list[Article], profile: dict) -> dict[str, list[Article]]:
    groups: dict[str, list[Article]] = {theme.get("name", "Tema"): [] for theme in profile_themes(profile)}
    for article in articles:
        groups.setdefault(article.category, []).append(article)
    return groups


def render_html(articles: list[Article], profile: dict, errors: list[str]) -> str:
    generated = now_local()
    themes = profile_themes(profile)
    groups = grouped(articles, profile)
    detected = profile.get("detected_interests") or [theme.get("name", "Tema") for theme in themes]

    style = """
    :root {
      color-scheme: light;
      --ink: #1c232b;
      --muted: #5f6975;
      --line: #d8dee5;
      --paper: #f6f7f9;
      --panel: #ffffff;
      --accent: #1b6aa8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background: var(--paper);
      line-height: 1.45;
    }
    header {
      background: #14202b;
      color: #fff;
      border-bottom: 5px solid #d49b42;
    }
    .wrap {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      padding: 30px 0 24px;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 46px);
      letter-spacing: 0;
      line-height: 1;
    }
    .meta {
      color: #cfdae4;
      text-align: right;
      font-size: 14px;
    }
    .summary-band {
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      padding: 16px 0;
    }
    .metric {
      border-left: 4px solid var(--accent);
      padding: 4px 10px;
      min-width: 0;
    }
    .metric b {
      display: block;
      font-size: 22px;
    }
    .metric span {
      color: var(--muted);
      font-size: 13px;
    }
    main {
      padding: 24px 0 34px;
    }
    section {
      margin: 0 0 28px;
    }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      border-bottom: 2px solid var(--line);
      padding-bottom: 8px;
      margin-bottom: 12px;
    }
    h2 {
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }
    .count {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .news-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .item {
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 5px solid var(--accent);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }
    .item h3 {
      margin: 0 0 8px;
      font-size: 17px;
      line-height: 1.25;
      letter-spacing: 0;
    }
    .item p {
      margin: 0 0 10px;
      color: #303943;
    }
    .item-footer {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      border-top: 1px solid #eef1f4;
      padding-top: 9px;
    }
    a {
      color: #145d96;
      text-decoration: none;
      overflow-wrap: anywhere;
    }
    a:hover { text-decoration: underline; }
    .notes {
      background: #fff;
      border-top: 1px solid var(--line);
      padding: 18px 0 24px;
      color: var(--muted);
      font-size: 13px;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .chip {
      border: 1px solid var(--line);
      background: #f9fafb;
      color: #2d3743;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
    }
    .warn {
      margin-top: 12px;
      color: #7d4a18;
    }
    @media (max-width: 760px) {
      .topbar, .summary-grid, .news-grid {
        grid-template-columns: 1fr;
      }
      .meta {
        text-align: left;
      }
    }
    """

    category_styles = "\n".join(
        f'.section-{idx} {{ --accent: {theme.get("accent", THEME_COLORS[idx % len(THEME_COLORS)])}; }}'
        for idx, theme in enumerate(themes)
    )

    sections = []
    for idx, theme in enumerate(themes):
        name = theme.get("name", "Tema")
        items = groups.get(name, [])
        cards = []
        for number, article in enumerate(items, start=1):
            title = html.escape(article.title)
            summary = html.escape(make_summary(article))
            source = html.escape(article.source or "Fuente no indicada")
            published = html.escape(format_date(article.published))
            link = html.escape(article.link)
            if article.link:
                source_html = f'<a href="{link}" target="_blank" rel="noopener">{source}</a>'
            else:
                source_html = source
            cards.append(
                f"""
                <article class="item">
                  <h3>{number}. {title}</h3>
                  <p>{summary}</p>
                  <div class="item-footer">
                    <span>{published}</span>
                    <span>{source_html}</span>
                  </div>
                </article>
                """
            )
        sections.append(
            f"""
            <section class="section-{idx}">
              <div class="section-head">
                <h2>{html.escape(name)}</h2>
                <span class="count">{len(items)} noticias</span>
              </div>
              <div class="news-grid">
                {''.join(cards)}
              </div>
            </section>
            """
        )

    chips = "".join(f'<span class="chip">{html.escape(item)}</span>' for item in detected)
    error_html = ""
    if errors:
        sample = "; ".join(errors[:4])
        error_html = f'<p class="warn">Avisos RSS: {html.escape(shorten_chars(sample, 420))}</p>'

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{AGENT_NAME} - Resumen diario</title>
  <style>{style}{category_styles}</style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>{AGENT_NAME}</h1>
        <div>Resumen diario de mis noticias por tematica</div>
      </div>
      <div class="meta">
        <div>{generated.strftime("%A %d/%m/%Y")}</div>
        <div>Generado {generated.strftime("%H:%M")}</div>
      </div>
    </div>
  </header>
  <div class="summary-band">
    <div class="wrap summary-grid">
      <div class="metric"><b>{len(articles)}</b><span>noticias seleccionadas</span></div>
      <div class="metric"><b>{ITEMS_PER_THEME}</b><span>noticias por tematica</span></div>
      <div class="metric"><b>{SCHEDULE_TIME_LABEL}</b><span>inicio programado diario</span></div>
      <div class="metric"><b>{len(themes)}</b><span>tematicas configuradas</span></div>
    </div>
  </div>
  <main class="wrap">
    {''.join(sections)}
  </main>
  <footer class="notes">
    <div class="wrap">
      <strong>Tematicas configuradas:</strong>
      <div class="chips">{chips}</div>
      <p>{html.escape(profile.get("privacy", ""))}</p>
      {error_html}
    </div>
  </footer>
</body>
</html>
"""


def write_report(html_text: str) -> Path:
    ensure_dirs()
    report_path = LATEST_PATH
    report_path.write_text(html_text, encoding="utf-8")
    return report_path


def open_report(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    webbrowser.open(path.as_uri())


def offline_demo_articles(profile: dict) -> list[Article]:
    today = now_local()
    demo: list[Article] = []
    for theme in profile_themes(profile):
        name = theme.get("name", "Tema")
        target = int(theme.get("target", ITEMS_PER_THEME))
        queries = theme.get("queries", [name])
        for idx in range(target):
            demo.append(
                Article(
                    category=name,
                    query=queries[idx % len(queries)],
                    title=f"Ejemplo {idx + 1} para {name}",
                    link="https://news.google.com/",
                    source="Demo local",
                    description=(
                        "Resumen de prueba para validar el HTML con las tematicas configuradas "
                        "antes de activar la ejecucion con internet."
                    ),
                    published=today,
                )
            )
    return demo


def run(args: argparse.Namespace) -> int:
    ensure_dirs()
    start = time.time()
    profile = load_or_create_profile(force=args.refresh_profile)
    if args.profile_only:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return 0

    if args.offline_demo:
        articles = offline_demo_articles(profile)
        errors = []
    else:
        articles_raw, errors = collect_articles(profile)
        selected = choose_articles(articles_raw, profile)
        if len(selected) < target_total(profile):
            missing = target_total(profile) - len(selected)
            errors.append(
                f"No se reunieron {target_total(profile)} noticias verificables; "
                f"se completaron {missing} espacios con temas de monitoreo."
            )
        articles = complete_article_targets(selected, profile)

    html_text = render_html(articles, profile, errors)
    report_path = write_report(html_text)
    elapsed = time.time() - start
    log(f"Report generated: {report_path} in {elapsed:.1f}s with {len(articles)} items")

    if not args.no_open:
        open_report(report_path)
    print(str(report_path))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent News daily fixed-topic briefing.")
    parser.add_argument("--no-open", action="store_true", help="Generate the report without opening it.")
    parser.add_argument("--offline-demo", action="store_true", help="Generate a local demo report without internet.")
    parser.add_argument("--profile-only", action="store_true", help="Show the configured topic profile and exit.")
    parser.add_argument("--refresh-profile", action="store_true", help="Rebuild the configured topic profile.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args(sys.argv[1:])))
    except Exception as exc:
        log(f"Fatal error: {exc}")
        raise
