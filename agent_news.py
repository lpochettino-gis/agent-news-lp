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
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from news_images import enrich_images


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
RADIO_SCRIPT_PATH = OUTPUT_DIR / "agent_news_radio_briefing.txt"
RADIO_WAV_PATH = OUTPUT_DIR / "agent_news_radio_briefing.wav"

HTTP_TIMEOUT_SECONDS = 12
MAX_WORKERS = 10
ITEMS_PER_THEME = 4
ITEMS_PER_GROUP = 8
TREND_ITEMS_PER_GROUP = 10
RADIO_PLAYBACK_RATE = 1.5
RADIO_TARGET_MINUTES = 10
FAST_READ_ITEMS = 12
RADIO_ARTICLE_LIMIT = 20
RADIO_TREND_ITEMS_PER_GROUP = 5
REPORT_ITEMS = 56
PROFILE_VERSION = 5
THEME_COUNT = 18
QUERIES_PER_THEME = 4
SCHEDULE_TIME_LABEL = "08:30"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) AgentNews/1.0"
)

RSS_LOCALES = (
    {"hl": "es-419", "gl": "AR", "ceid": "AR:es-419"},
    {"hl": "en-US", "gl": "US", "ceid": "US:en"},
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
        "keywords": ["equipamiento topografico", "gnss", "rtk", "lidar", "estacion total", "geospatial"],
        "queries": [
            "equipamiento topografico noticias novedades",
            "GNSS GPS RTK topografia noticias",
            "estaciones totales scanners laser LiDAR novedades",
            "surveying equipment news today",
            "drone mapping LiDAR news",
            "geospatial technology news",
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

TOPIC_GROUP_DEFINITIONS = [
    {
        "name": "Argentina",
        "target": ITEMS_PER_GROUP,
        "accent": "#00e5ff",
        "categories": ["Argentina"],
    },
    {
        "name": "Energía y Recursos",
        "target": ITEMS_PER_GROUP,
        "accent": "#ffb02e",
        "categories": ["Petroleo", "Gas", "Litio"],
    },
    {
        "name": "Drones y Topografía",
        "target": ITEMS_PER_GROUP,
        "accent": "#22f2a6",
        "categories": ["Drones", "Equipamiento Topografico"],
    },
    {
        "name": "Software e IA",
        "target": ITEMS_PER_GROUP,
        "accent": "#ff4fd8",
        "categories": ["Software SAAS", "Inteligencia artificial"],
    },
    {
        "name": "Tech y Hardware",
        "target": ITEMS_PER_GROUP,
        "accent": "#4b7dff",
        "categories": ["Novedades Tech", "Ultimos Gadgets", "Robots"],
    },
]

AGRO_GROUP = "Agro"
LOCAL_GROUP = "Zona · Pasteur y región"
# Cobertura editorial aproximada, por localidades; no es un geocercado de cada hecho.
LOCAL_TOWNS = (
    "Pasteur", "Lincoln", "General Villegas", "Pehuajó", "General Pinto",
    "Florentino Ameghino", "Rivadavia", "América", "Carlos Tejedor",
    "Trenque Lauquen", "Carlos Casares", "Nueve de Julio", "9 de Julio",
    "Junín", "Leandro N. Alem", "Vedia", "Los Toldos", "General Viamonte",
    "Bragado", "Chacabuco", "Chivilcoy", "Bolívar", "Daireaux",
    "General Pico", "Intendente Alvear", "Rufino", "Laboulaye",
)
LOCAL_SOURCES = (
    "Diario Democracia", "La Posta del Noroeste", "Distrito Interior",
    "Diario Actualidad", "Diario Noticias Pehuajó", "Noticias Pehuajó",
    "Oeste BA", "OesteBA", "La Opinión de Trenque Lauquen",
    "Municipalidad de Lincoln", "Municipalidad de General Villegas",
)
LOCAL_CATEGORIES = ("Pasteur", "Lincoln", "General Villegas", "Pehuajó", "Región cercana")
FIXED_THEME_DEFINITIONS.extend([
    {
        "name": "Agricultura y mercados",
        "keywords": ["agro", "agricultura", "soja", "maiz", "trigo", "girasol", "cosecha", "siembra"],
        "queries": [
            'Argentina agro (soja OR maíz OR trigo OR girasol) precios cosecha',
            'Argentina agricultura (lluvias OR sequía OR inundaciones OR heladas)',
            'Argentina agro (maquinaria OR agtech OR "agricultura de precisión")',
            'Argentina agro (INTA OR "Bolsa de Cereales" OR "Bolsa de Comercio de Rosario")',
        ],
    },
    {
        "name": "Ganadería y lechería",
        "keywords": ["ganaderia", "lecheria", "tambos", "hacienda", "carne", "leche", "senasa"],
        "queries": [
            'Argentina (ganadería OR hacienda) (precios OR producción OR mercado)',
            'Argentina (lechería OR tambos) (leche OR costos OR producción)',
            'Argentina SENASA (bovinos OR sanidad OR vacunación)',
            'Argentina agro (retenciones OR exportaciones OR insumos OR "caminos rurales")',
        ],
    },
    *[
        {"name": town, "keywords": [town], "queries": [
            f'"{town}" "Buenos Aires"',
            f'"{town}" (municipalidad OR rural OR obras OR salud OR educación OR deportes)',
        ]}
        for town in LOCAL_CATEGORIES[:4]
    ],
    {
        "name": "Región cercana", "keywords": list(LOCAL_TOWNS[4:]),
        "queries": [
            '("General Pinto" OR "Florentino Ameghino" OR "Carlos Tejedor" OR "Rivadavia" OR "América") "Buenos Aires"',
            '("Trenque Lauquen" OR "Carlos Casares" OR "Nueve de Julio" OR "9 de Julio" OR "Bolívar" OR "Daireaux") noticias',
            '("Junín" OR "Vedia" OR "Los Toldos" OR "Bragado" OR "Chacabuco" OR "Chivilcoy" OR "General Viamonte" OR "Leandro N. Alem") "Buenos Aires"',
            '("General Pico" OR "Intendente Alvear" OR "Rufino" OR "Laboulaye") noticias',
        ],
    },
])
TOPIC_GROUP_DEFINITIONS.extend([
    {"name": AGRO_GROUP, "target": ITEMS_PER_GROUP, "accent": "#a3e635",
     "categories": ["Agricultura y mercados", "Ganadería y lechería"],
     "description": "Agricultura, ganadería, lechería, mercados, clima y tecnología del agro argentino. Últimas 24 horas."},
    {"name": LOCAL_GROUP, "target": ITEMS_PER_GROUP, "accent": "#fb923c",
     "categories": list(LOCAL_CATEGORIES),
     "description": "Pasteur como centro · cobertura aproximada de 250 km por localidades. Prioridad: Pasteur, Lincoln, General Villegas y Pehuajó. Últimas 72 horas, con fecha y fuente."},
])

TREND_GROUP_DEFINITIONS = [
    {
        "name": "Argentina",
        "target": TREND_ITEMS_PER_GROUP,
        "accent": "#00e5ff",
        "geo": "AR",
        "queries": [
            "Argentina tendencias hoy redes sociales",
            "Argentina hashtags tendencia hoy",
            "Argentina temas tendencia ultimas horas",
            "Argentina viral actualidad hoy",
        ],
    },
    {
        "name": "Global",
        "target": TREND_ITEMS_PER_GROUP,
        "accent": "#ffb02e",
        "geo": "",
        "queries": [
            "global trends today social media",
            "world trending hashtags today",
            "viral topics today worldwide",
            "breaking trends today",
        ],
    },
    {
        "name": "Tech",
        "target": TREND_ITEMS_PER_GROUP,
        "accent": "#ff4fd8",
        "geo": "US",
        "queries": [
            "technology trends today AI gadgets",
            "tech hashtags trending today",
            "AI software robotics drones trends today",
            "startup technology viral news today",
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
class TrendItem:
    group: str
    title: str
    link: str
    source: str
    description: str
    published: dt.datetime | None
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
    # Fix mojibake: UTF-8 bytes that were incorrectly decoded as Latin-1
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
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


def normalized_match_text(value: str) -> str:
    value = strip_accents(value).lower()
    return compact_spaces(re.sub(r"[^a-z0-9]+", " ", value))


def contains_terms(text: str, terms: tuple[str, ...]) -> bool:
    padded = f" {normalized_match_text(text)} "
    tokens = set(padded.split())
    for term in terms:
        normalized = normalized_match_text(term)
        if not normalized:
            continue
        if " " in normalized:
            if f" {normalized} " in padded:
                return True
        elif normalized in tokens:
            return True
    return False


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


def rss_url(query: str, locale: dict[str, str] | None = None, days: int = 1) -> str:
    query_with_window = f"{query} when:{days}d"
    locale = locale or RSS_LOCALES[0]
    params = {
        "q": query_with_window,
        "hl": locale["hl"],
        "gl": locale["gl"],
        "ceid": locale["ceid"],
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


def read_url(req: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.URLError:
        if not urllib.request.getproxies():
            raise
        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direct_opener.open(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.read()


def parse_feed_items(category: str, query: str, data: bytes) -> list[Article]:
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


def fetch_feed(category: str, query: str) -> list[Article]:
    first_error: Exception | None = None
    for locale in RSS_LOCALES:
        url = rss_url(query, locale, days=3 if category in LOCAL_CATEGORIES else 1)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            items = parse_feed_items(category, query, read_url(req))
        except Exception as exc:
            if first_error is None:
                first_error = exc
            continue
        if items:
            return items
    if first_error is not None:
        raise first_error
    return []


def trends_rss_url(geo: str) -> str:
    return "https://trends.google.com/trending/rss?" + urllib.parse.urlencode({"geo": geo})


def child_text_by_suffix(parent: ET.Element, suffix: str) -> str:
    suffix = suffix.lower()
    for child in parent.iter():
        tag = child.tag.lower()
        if tag.endswith(suffix) and child.text:
            return clean_text(child.text)
    return ""


def parse_google_trends_items(group_name: str, data: bytes) -> list[TrendItem]:
    root = ET.fromstring(data)
    items: list[TrendItem] = []
    for item in root.findall("./channel/item"):
        title = clean_text(xml_text(item, "title"))
        link = xml_text(item, "link")
        published = parse_date(xml_text(item, "pubDate"))
        traffic = child_text_by_suffix(item, "approx_traffic")
        description = clean_text(xml_text(item, "description"))
        if traffic:
            description = compact_spaces(f"Volumen aproximado: {traffic}. {description}")
        if not title:
            continue
        items.append(
            TrendItem(
                group=group_name,
                title=title,
                link=link,
                source="Google Trends",
                description=description or "Tema detectado como tendencia en busquedas recientes.",
                published=published,
                score=3.0,
            )
        )
    return items


def trend_items_from_news(group_name: str, query: str) -> list[TrendItem]:
    items: list[TrendItem] = []
    for article in fetch_feed(group_name, query):
        items.append(
            TrendItem(
                group=group_name,
                title=article.title,
                link=article.link,
                source=article.source or "Google News",
                description=article.description,
                published=article.published,
                score=article.score,
            )
        )
    return items


def rank_trend_items(items: list[TrendItem], limit: int) -> list[TrendItem]:
    ranked: list[TrendItem] = []
    seen: set[str] = set()
    for item in items:
        key = item.key
        if not key or key in seen:
            continue
        seen.add(key)
        ranked.append(item)
        if len(ranked) >= limit:
            break
    return ranked


def fallback_trend_items(group_name: str, limit: int) -> list[TrendItem]:
    today = now_local()
    return [
        TrendItem(
            group=group_name,
            title=f"{group_name} trend monitor #{index + 1}",
            link="",
            source="Monitor local",
            description="No se obtuvo una senal publica suficiente; se deja el espacio para mantener el tablero completo.",
            published=today,
            score=0.0,
        )
        for index in range(limit)
    ]


def collect_trends(profile: dict) -> tuple[dict[str, list[TrendItem]], list[str]]:
    trend_map: dict[str, list[TrendItem]] = {}
    errors: list[str] = []
    for group in profile_trend_groups(profile):
        name = group.get("name", "Trends")
        target = int(group.get("target", TREND_ITEMS_PER_GROUP))
        items: list[TrendItem] = []

        geo = str(group.get("geo", ""))
        try:
            req = urllib.request.Request(trends_rss_url(geo), headers={"User-Agent": USER_AGENT})
            items.extend(parse_google_trends_items(name, read_url(req)))
        except Exception as exc:
            errors.append(f"Trends {name}: Google Trends RSS ({exc})")

        if len(rank_trend_items(items, target)) < target:
            for query in group.get("queries", []):
                try:
                    items.extend(trend_items_from_news(name, query))
                except Exception as exc:
                    errors.append(f"Trends {name}: {query} ({exc})")
                    continue
                if len(rank_trend_items(items, target)) >= target:
                    break

        ranked = rank_trend_items(items, target)
        if len(ranked) < target:
            ranked.extend(fallback_trend_items(name, target - len(ranked)))
        trend_map[name] = ranked[:target]

    return trend_map, errors


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


def build_topic_groups() -> list[dict]:
    return [dict(group) for group in TOPIC_GROUP_DEFINITIONS]


def build_trend_groups() -> list[dict]:
    return [dict(group) for group in TREND_GROUP_DEFINITIONS]


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


def profile_topic_groups(profile: dict) -> list[dict]:
    groups = profile.get("topic_groups")
    if isinstance(groups, list) and groups:
        return groups
    return build_topic_groups()


def profile_trend_groups(profile: dict) -> list[dict]:
    groups = profile.get("trend_groups")
    if isinstance(groups, list) and groups:
        return groups
    return build_trend_groups()


def article_group_name(category: str, profile: dict) -> str:
    for group in profile_topic_groups(profile):
        name = group.get("name", "Tema")
        categories = group.get("categories", [])
        if category == name or category in categories:
            return name
    return category


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
        "topic_groups": build_topic_groups(),
        "trend_groups": build_trend_groups(),
        "themes": [theme.to_dict() for theme in themes],
        "local_coverage": {"center": "Pasteur, Lincoln, Buenos Aires", "radius_km_approx": 250,
                           "mode": "editorial_locality_list", "towns": list(LOCAL_TOWNS),
                           "priority_towns": list(LOCAL_CATEGORIES[:4]), "max_age_hours": 72},
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
                and profile.get("topic_groups")
                and profile.get("trend_groups")
            ):
                return profile
    profile = build_interest_profile()
    save_profile(profile)
    return profile


def local_article_matches(article: Article) -> bool:
    # La consulta y el nombre del medio no prueban dónde ocurrió la noticia.
    text = remove_source_noise(f"{article.title} {article.description}", article.source)
    ambiguous = {"pasteur", "lincoln", "america", "rivadavia", "junin", "9 de julio", "nueve de julio", "bolivar"}
    towns = (article.category,) if article.category in LOCAL_CATEGORIES[:4] else LOCAL_TOWNS
    matches = [town for town in towns if contains_terms(text, (town,))]
    if not matches:
        return False
    # América también nombra al continente y Rivadavia a calles de todo el país.
    if all(normalized_match_text(town) in {"america", "rivadavia"} for town in matches):
        return (contains_terms(text, ("ciudad de america", "localidad de america", "america rivadavia",
                                     "partido de rivadavia", "municipalidad de rivadavia", "rivadavia bonaerense"))
                or (contains_terms(text, ("america",)) and contains_terms(text, ("rivadavia",))))
    if any(normalized_match_text(town) not in ambiguous for town in matches):
        return True
    # Evita Louis Pasteur, Abraham Lincoln y ciudades homónimas fuera de la zona.
    corroboration = ("Buenos Aires", "bonaerense", "linqueño", "linqueña", "pasteurense")
    return (contains_terms(text, corroboration)
            or contains_terms(article.source, LOCAL_SOURCES)
            or contains_terms(text, tuple(t for t in LOCAL_TOWNS if normalized_match_text(t) not in ambiguous)))


def article_in_scope(article: Article) -> bool:
    if article.category not in (*LOCAL_CATEGORIES, "Agricultura y mercados", "Ganadería y lechería"):
        return True
    if article.published is None:
        return False
    age = (now_local() - article.published).total_seconds() / 3600
    if age < -1 or age > (72 if article.category in LOCAL_CATEGORIES else 24):
        return False
    if article.category in LOCAL_CATEGORIES:
        return local_article_matches(article)
    text = remove_source_noise(f"{article.title} {article.description}", article.source)
    argentina_context = ("argentina", "argentino", "argentinos", "argentinas", "bonaerense", "pampeano",
                         "Buenos Aires", "Córdoba", "Santa Fe", "Entre Ríos", "La Pampa", "SENASA",
                         "INTA", "Bolsa de Cereales", "Bolsa de Comercio de Rosario")
    if not contains_terms(text, argentina_context):
        return False
    if article.category == "Ganadería y lechería":
        return contains_terms(text, ("ganaderia", "ganadero", "ganaderos", "hacienda", "bovinos", "vacunos",
                                     "carne", "leche", "lecheria", "lechera", "lactea", "tambos", "tambo"))
    return True


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
            collected.extend(article for article in articles if article_in_scope(article))
    return collected, errors


def choose_articles(articles: list[Article], profile: dict) -> list[Article]:
    topic_groups = profile_topic_groups(profile)
    by_group: dict[str, list[Article]] = {group.get("name", "Tema"): [] for group in topic_groups}
    targets = {group.get("name", "Tema"): int(group.get("target", ITEMS_PER_GROUP)) for group in topic_groups}
    global_seen: set[str] = set()

    ranked = sorted((a for a in articles if article_in_scope(a)), key=lambda item: item.score, reverse=True)
    # Reserva una noticia por subtema nuevo cuando hay material, antes de llenar cupos.
    for category in ("Agricultura y mercados", "Ganadería y lechería", *LOCAL_CATEGORIES):
        for article in ranked:
            if article.category == category and article.key and article.key not in global_seen:
                group_name = article_group_name(category, profile)
                if group_name in by_group and len(by_group[group_name]) < targets[group_name]:
                    by_group[group_name].append(article)
                    global_seen.add(article.key)
                break

    for article in ranked:
        key = article.key
        if not key or key in global_seen:
            continue
        group_name = article_group_name(article.category, profile)
        if group_name in by_group and len(by_group[group_name]) < targets[group_name]:
            by_group[group_name].append(article)
            global_seen.add(key)

    selected: list[Article] = []
    for group in topic_groups:
        name = group.get("name", "Tema")
        selected.extend(by_group.get(name, []))

    return selected


def fallback_articles(profile: dict) -> list[Article]:
    today = now_local()
    topics: list[tuple[str, str]] = []
    for group in profile_topic_groups(profile):
        name = group.get("name", "Tema")
        target = int(group.get("target", ITEMS_PER_GROUP))
        for index in range(target):
            topics.append((name, f"{name}: noticia pendiente {index + 1}"))
    return [
        Article(
            category=category,
            query=topic,
            title=topic,
            link="",
            source="Sin noticias verificables",
            description="No se pudo obtener una noticia verificable para esta tematica en esta ejecucion. El agente dejo este espacio como recordatorio de busqueda.",
            published=today,
            score=0.0,
        )
        for category, topic in topics
    ]


def target_total(profile: dict) -> int:
    return sum(int(group.get("target", ITEMS_PER_GROUP)) for group in profile_topic_groups(profile))


def complete_article_targets(articles: list[Article], profile: dict) -> list[Article]:
    topic_groups = profile_topic_groups(profile)
    targets = {group.get("name", "Tema"): int(group.get("target", ITEMS_PER_GROUP)) for group in topic_groups}
    selected: list[Article] = []
    selected_keys: set[str] = set()
    counts: Counter = Counter()

    for group in topic_groups:
        name = group.get("name", "Tema")
        target = targets[name]
        for article in articles:
            if article_group_name(article.category, profile) != name or counts[name] >= target:
                continue
            if article.key in selected_keys:
                continue
            selected.append(article)
            selected_keys.add(article.key)
            counts[name] += 1

    for fallback in fallback_articles(profile):
        name = article_group_name(fallback.category, profile)
        if counts[name] >= targets.get(name, ITEMS_PER_GROUP):
            continue
        if fallback.key in selected_keys:
            continue
        selected.append(fallback)
        selected_keys.add(fallback.key)
        counts[name] += 1

    return selected


def infer_problem(article: Article) -> str:
    text = f"{article.title} {article.description}"
    if contains_terms(text, ("precio", "mercado", "cotizacion", "sube", "baja", "cae", "dolar")):
        return "impacto economico o de mercado"
    if contains_terms(text, ("gobierno", "ley", "regulacion", "politica", "congreso", "justicia")):
        return "decision politica o regulatoria"
    if contains_terms(text, ("inversion", "proyecto", "obra", "licitacion", "financiacion")):
        return "inversion, ejecucion y riesgo de proyecto"
    if contains_terms(text, ("petroleo", "gas", "litio", "energia", "vaca muerta", "gnl")):
        return "produccion, abastecimiento y precios de recursos"
    if contains_terms(text, ("dron", "drones", "uav", "topografia", "gnss", "rtk", "lidar")):
        return "automatizacion, medicion y operacion en campo"
    if contains_terms(text, ("ia", "ai", "software", "saas", "modelo", "modelos", "startup", "startups", "cloud")):
        return "adopcion tecnologica y competencia"
    if contains_terms(text, ("robot", "robots", "robotica", "automatizacion", "humanoide", "humanoides")):
        return "automatizacion y productividad"
    if contains_terms(text, ("seguridad", "accidente", "riesgo", "crisis", "conflicto")):
        return "riesgo operativo o seguridad"
    return "hecho central y su impacto inmediato"


def remove_source_noise(value: str, source: str) -> str:
    value = compact_spaces(value)
    if not source:
        return value
    candidates = {
        source,
        source.replace("www.", ""),
        source.removeprefix("www."),
    }
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate:
            value = re.sub(re.escape(candidate), " ", value, flags=re.I)
    value = re.sub(r"\s+-\s+Noticias\s+Argentina\s*$", " ", value, flags=re.I)
    value = re.sub(r"\s+Noticias\s+Argentina\s*$", " ", value, flags=re.I)
    return compact_spaces(value).rstrip("-| ")


def article_context_text(article: Article) -> str:
    title = remove_source_noise(article.title, article.source)
    description = remove_source_noise(article.description, article.source)
    if description.lower().startswith(title.lower()[: max(20, min(80, len(title)))]):
        text = description
    elif title and title.lower() in description.lower():
        text = description
    elif title and description:
        text = f"{title}. {description}"
    else:
        text = title or description
    return compact_spaces(text)


def problem_explanation(problem: str) -> str:
    explanations = {
        "impacto economico o de mercado": "La clave es medir si modifica precios, expectativas de mercado o decisiones de inversion en el corto plazo.",
        "decision politica o regulatoria": "La clave es entender que actores quedan condicionados y si la decision cambia reglas, prioridades o costos.",
        "inversion, ejecucion y riesgo de proyecto": "La clave es seguir plazos, financiamiento, permisos y capacidad real de ejecucion.",
        "produccion, abastecimiento y precios de recursos": "La clave es evaluar si afecta oferta, infraestructura, costos o competitividad del sector.",
        "automatizacion, medicion y operacion en campo": "La clave es ver si mejora productividad, seguridad, precision o reduce tiempos operativos.",
        "adopcion tecnologica y competencia": "La clave es ver quien gana capacidad, que herramienta se vuelve relevante y que modelos quedan presionados.",
        "automatizacion y productividad": "La clave es medir si reemplaza tareas, acelera procesos o cambia la escala operativa.",
        "riesgo operativo o seguridad": "La clave es identificar exposicion, responsables y posibles medidas de mitigacion.",
    }
    return explanations.get(problem, "La clave es entender que cambia, a quien afecta y si el tema gana peso en la agenda inmediata.")


def problem_subject(problem: str) -> str:
    subjects = {
        "impacto economico o de mercado": "un impacto economico o de mercado",
        "decision politica o regulatoria": "una decision politica o regulatoria",
        "inversion, ejecucion y riesgo de proyecto": "inversion, ejecucion y riesgo de proyecto",
        "produccion, abastecimiento y precios de recursos": "produccion, abastecimiento y precios de recursos",
        "automatizacion, medicion y operacion en campo": "automatizacion, medicion y operacion en campo",
        "adopcion tecnologica y competencia": "adopcion tecnologica y competencia",
        "automatizacion y productividad": "automatizacion y productividad",
        "riesgo operativo o seguridad": "riesgo operativo o seguridad",
        "hecho central y su impacto inmediato": "un hecho de actualidad con impacto inmediato",
    }
    return subjects.get(problem, problem)


def problem_short_label(problem: str) -> str:
    labels = {
        "impacto economico o de mercado": "Mercado",
        "decision politica o regulatoria": "Regulacion",
        "inversion, ejecucion y riesgo de proyecto": "Inversion",
        "produccion, abastecimiento y precios de recursos": "Recursos",
        "automatizacion, medicion y operacion en campo": "Operaciones",
        "adopcion tecnologica y competencia": "Tecnologia",
        "automatizacion y productividad": "Automatizacion",
        "riesgo operativo o seguridad": "Riesgo",
    }
    return labels.get(problem, "")


def make_summary(article: Article, topic_name: str | None = None) -> str:
    title = remove_source_noise(article.title, article.source)
    description = remove_source_noise(article.description or "", article.source)
    if normalize_for_key(description) == normalize_for_key(title):
        return ""
    return shorten_chars(description, 420)



def is_real_article(article: Article) -> bool:
    source = strip_accents(article.source or "").lower()
    return bool(article.link) and source not in {"sin conexion", "sin noticias verificables", "demo local"} and "noticia pendiente" not in article.title.lower()


def article_title_clean(article: Article) -> str:
    return shorten_chars(remove_source_noise(article.title, article.source), 160)


def action_suggestion(article: Article, group_name: str) -> str:
    problem = infer_problem(article)
    group_key = strip_accents(group_name).lower()
    if group_name == AGRO_GROUP:
        return "revisar el efecto en costos, campaña, sanidad y trabajo en el campo."
    if group_name == LOCAL_GROUP:
        return "revisar la localidad y la fecha; seguir efectos en caminos, servicios, producción y agenda de la zona."
    if group_key == "argentina":
        return "mirar si cambia agenda publica, costos o reglas de negocio."
    if group_key == "energia y recursos":
        return "seguir impacto en precios, infraestructura, permisos y oportunidades de proveedores."
    if group_key == "drones y topografia":
        return "evaluar si aparece una herramienta, sensor o uso de campo replicable."
    if group_key == "software e ia":
        return "revisar si la tecnologia puede automatizar trabajo propio o crear un producto."
    if group_key == "tech y hardware":
        return "detectar si es una senal temprana de mercado o solo ruido de consumo."
    if problem == "riesgo operativo o seguridad":
        return "identificar responsables, exposicion y mitigaciones."
    return "guardarlo como senal y revisar si se repite en proximas ediciones."


def briefing_item(article: Article, profile: dict) -> dict:
    group_name = article_group_name(article.category, profile)
    problem = infer_problem(article)
    title = article_title_clean(article).rstrip(". ")
    return {
        "group": group_name,
        "category": article.category,
        "title": title,
        "problem": problem,
        "why": problem_explanation(problem),
        "action": action_suggestion(article, group_name),
        "source": article.source or "Fuente no indicada",
        "published": format_date(article.published),
    }


def unique_briefing_items(articles: list[Article], profile: dict, limit: int) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for article in sorted((item for item in articles if is_real_article(item)), key=lambda item: item.score, reverse=True):
        key = article.key
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(briefing_item(article, profile))
        if len(items) >= limit:
            break
    return items


def filtered_briefing_items(articles: list[Article], profile: dict, problems: set[str], limit: int) -> list[dict]:
    selected = [
        article
        for article in articles
        if is_real_article(article) and infer_problem(article) in problems
    ]
    return unique_briefing_items(selected, profile, limit)


def balanced_articles(articles: list[Article], profile: dict, limit: int) -> list[Article]:
    ranked = sorted((a for a in articles if is_real_article(a)), key=lambda a: a.score, reverse=True)
    selected: list[Article] = []
    seen: set[str] = set()
    for offset in range(2):
        for group in profile_topic_groups(profile):
            candidates = [a for a in ranked if article_group_name(a.category, profile) == group["name"]]
            if offset >= len(candidates):
                continue
            article = candidates[offset]
            if article.key not in seen and len(selected) < limit:
                selected.append(article)
                seen.add(article.key)
    for article in ranked:
        if article.key not in seen and len(selected) < limit:
            selected.append(article)
            seen.add(article.key)
    return selected


def build_briefing(articles: list[Article], profile: dict, trends: dict[str, list[TrendItem]]) -> dict:
    risk_problems = {
        "decision politica o regulatoria",
        "riesgo operativo o seguridad",
        "impacto economico o de mercado",
    }
    opportunity_problems = {
        "inversion, ejecucion y riesgo de proyecto",
        "adopcion tecnologica y competencia",
        "automatizacion, medicion y operacion en campo",
        "automatizacion y productividad",
    }
    radar: list[dict] = []
    for group in profile_topic_groups(profile):
        group_name = group.get("name", "Tema")
        group_articles = [
            article
            for article in articles
            if is_real_article(article) and article_group_name(article.category, profile) == group_name
        ]
        if not group_articles:
            continue
        top = sorted(group_articles, key=lambda item: item.score, reverse=True)[0]
        radar.append(briefing_item(top, profile))

    trend_watch = []
    for name, items in trends.items():
        clean_items = [item for item in items if item.source != "Monitor local"]
        if clean_items:
            trend_watch.append({"group": name, "title": shorten_chars(clean_items[0].title, 120)})

    return {
        "top": unique_briefing_items(articles, profile, 5),
        "fast_read": [briefing_item(a, profile) for a in balanced_articles(articles, profile, FAST_READ_ITEMS)],
        "risks": filtered_briefing_items(articles, profile, risk_problems, 3),
        "opportunities": filtered_briefing_items(articles, profile, opportunity_problems, 3),
        "radar": radar,
        "trends": trend_watch[:3],
    }


def speech_text(value: str) -> str:
    replacements = {
        " IA ": " inteligencia artificial ",
        " AI ": " inteligencia artificial ",
        " SaaS ": " software como servicio ",
        " GNSS ": " geonavegacion satelital ",
        " RTK ": " erre te ka ",
        " GNL ": " gas natural licuado ",
        " WTI ": " doble ve te i ",
        " USD ": " dolares ",
    }
    lines: list[str] = []
    for raw_line in value.splitlines():
        line = html.unescape(clean_text(raw_line))
        padded = f" {line} "
        for key, replacement in replacements.items():
            padded = padded.replace(key, replacement)
        line = re.sub(r"https?://\S+", " ", padded.strip())
        lines.append(compact_spaces(line))
    return "\n".join(lines).strip()


def radio_article_line(article: Article, profile: dict, number: int) -> str:
    group_name = article_group_name(article.category, profile)
    problem = infer_problem(article)
    title = article_title_clean(article).rstrip(". ")
    context = shorten_chars(article_context_text(article), 290).rstrip(". ")
    context_sentence = ""
    if normalize_for_key(context) != normalize_for_key(title):
        context_sentence = f" Contexto: {context}."
    source_sentence = f" Fuente principal: {article.source}." if article.source else ""
    if group_name == LOCAL_GROUP and article.published:
        source_sentence += f" Publicada el {article.published.strftime('%d/%m a las %H:%M')}."
    return (
        f"{number}. En {group_name}. {title}. "
        f"El tema de fondo es {problem_subject(problem)}.{context_sentence} "
        f"Por que importa: {problem_explanation(problem)} "
        f"{source_sentence} "
        f"Para tener en cuenta: {action_suggestion(article, group_name)} "
        "Si se repite en varios medios o varios dias, conviene pasarlo a seguimiento."
    )


def build_radio_briefing(
    articles: list[Article],
    profile: dict,
    trends: dict[str, list[TrendItem]],
    briefing: dict,
) -> str:
    generated = now_local()
    real_articles = [article for article in articles if is_real_article(article)]
    lines: list[str] = [
        f"Agent News Radio. Briefing del {generated.strftime('%d/%m/%Y')}, generado a las {generated.strftime('%H:%M')}.",
        "La idea es escucharlo como una radio rapida: primero lo importante, despues riesgos y oportunidades, y al final una ronda corta de noticias y tendencias.",
        "",
        "Apertura. Las cinco cosas que importan hoy.",
    ]

    for idx, item in enumerate(briefing.get("top", []), start=1):
        lines.append(
            f"{idx}. {item['group']}. {item['title']}. "
            f"Por que importa: {item['why']} Accion sugerida: {item['action']}"
        )

    lines.append("")
    lines.append("Riesgos a mirar.")
    for idx, item in enumerate(briefing.get("risks", []), start=1):
        lines.append(f"{idx}. {item['group']}. {item['title']}. {item['why']}")
    if not briefing.get("risks"):
        lines.append("No aparecen riesgos claros por encima del resto. Conviene mirar si esto cambia en la proxima ejecucion.")

    lines.append("")
    lines.append("Oportunidades o senales accionables.")
    for idx, item in enumerate(briefing.get("opportunities", []), start=1):
        lines.append(f"{idx}. {item['group']}. {item['title']}. {item['action']}")
    if not briefing.get("opportunities"):
        lines.append("No aparecen oportunidades fuertes. El valor esta en seguir la evolucion de los temas principales.")

    lines.append("")
    lines.append("Ronda rapida para enterarte en diez minutos.")
    for number, article in enumerate(
        balanced_articles(real_articles, profile, RADIO_ARTICLE_LIMIT),
        start=1,
    ):
        lines.append(radio_article_line(article, profile, number))

    for group_name in (AGRO_GROUP, LOCAL_GROUP):
        if not any(article_group_name(a.category, profile) == group_name for a in real_articles):
            lines.append(f"En {group_name}, no se obtuvieron noticias verificables en esta edición.")

    lines.append("")
    lines.append("Tendencias para tener en cuenta.")
    for trend_group in profile_trend_groups(profile):
        name = trend_group.get("name", "Trends")
        items = [item for item in trends.get(name, []) if item.source != "Monitor local"][:RADIO_TREND_ITEMS_PER_GROUP]
        if not items:
            continue
        lines.append(f"Tendencias {name}.")
        for idx, item in enumerate(items, start=1):
            description = shorten_chars(item.description or "Senal de tendencia detectada.", 150)
            lines.append(f"{idx}. {item.title}. {description}")

    lines.append("")
    lines.append("Cierre. Si solo recordas tres cosas: mira el primer bloque de cinco titulares, revisa los riesgos, y guarda las oportunidades que se repitan varios dias. Fin del briefing.")
    return speech_text("\n".join(lines))


def estimate_radio_minutes(script_text: str) -> float:
    words = len(re.findall(r"\b\w+\b", script_text))
    if words == 0:
        return 0.0
    words_per_minute_at_rate = 155 * RADIO_PLAYBACK_RATE
    return words / words_per_minute_at_rate


def ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def synthesize_radio_audio(script_path: Path, audio_path: Path) -> str:
    if os.name != "nt":
        return "Audio WAV no generado: la sintesis local esta implementada para Windows."
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$voice = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1; "
        "if ($voice) { $s.SelectVoice($voice.VoiceInfo.Name) }; "
        "$s.Rate = 0; "
        "$text = Get-Content -Raw -LiteralPath " + ps_single_quote(str(script_path)) + "; "
        "$s.SetOutputToWaveFile(" + ps_single_quote(str(audio_path)) + "); "
        "$s.Speak($text); "
        "$s.Dispose();"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=RADIO_TARGET_MINUTES * 90,
        )
    except Exception as exc:
        return f"WAV local no disponible; usa Narrar x1.5 en el navegador. Detalle: {exc}"
    if completed.returncode != 0:
        detail = compact_spaces(completed.stderr or completed.stdout or "PowerShell no devolvio detalle.")
        return f"WAV local no disponible; usa Narrar x1.5 en el navegador. Detalle: {shorten_chars(detail, 220)}"
    if not audio_path.exists():
        return "WAV local no disponible; usa Narrar x1.5 en el navegador."
    return ""


def write_radio_outputs(script_text: str) -> dict:
    ensure_dirs()
    RADIO_SCRIPT_PATH.write_text(script_text, encoding="utf-8")
    audio_error = synthesize_radio_audio(RADIO_SCRIPT_PATH, RADIO_WAV_PATH)
    return {
        "script_path": RADIO_SCRIPT_PATH,
        "audio_path": RADIO_WAV_PATH if RADIO_WAV_PATH.exists() and not audio_error else None,
        "audio_error": audio_error,
        "estimated_minutes": estimate_radio_minutes(script_text),
        "playback_rate": RADIO_PLAYBACK_RATE,
        "words": len(re.findall(r"\b\w+\b", script_text)),
        "script_text": script_text,
    }


def format_date(value: dt.datetime | None) -> str:
    if not value:
        return "Sin fecha"
    return value.strftime("%d/%m/%Y %H:%M")


def grouped(articles: list[Article], profile: dict) -> dict[str, list[Article]]:
    groups: dict[str, list[Article]] = {group.get("name", "Tema"): [] for group in profile_topic_groups(profile)}
    for article in articles:
        groups.setdefault(article_group_name(article.category, profile), []).append(article)
    return groups


def slug_id(value: str) -> str:
    slug = normalize_for_key(value).replace(" ", "-")
    return slug or "panel"


def render_html(
    articles: list[Article],
    profile: dict,
    errors: list[str],
    trends: dict[str, list[TrendItem]] | None = None,
    briefing: dict | None = None,
    radio_info: dict | None = None,
) -> str:
    generated = now_local()
    topic_groups = profile_topic_groups(profile)
    trend_groups = profile_trend_groups(profile)
    article_groups = grouped(articles, profile)
    trends = trends or {}
    detected = profile.get("detected_interests") or [theme.get("name", "Tema") for theme in profile_themes(profile)]
    trend_count = sum(len(items) for items in trends.values())

    style = """
    :root {
      color-scheme: dark;
      --bg: #05070d;
      --panel: rgba(9, 16, 28, 0.92);
      --panel-strong: rgba(12, 24, 42, 0.98);
      --ink: #e9fbff;
      --muted: #8ea6b8;
      --line: rgba(0, 229, 255, 0.24);
      --accent: #00e5ff;
      --blue: #4b7dff;
      --amber: #ffb02e;
      --magenta: #ff4fd8;
      --green: #22f2a6;
    }
    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body {
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(0, 229, 255, 0.06) 1px, transparent 1px),
        linear-gradient(rgba(0, 229, 255, 0.05) 1px, transparent 1px),
        linear-gradient(135deg, rgba(75, 125, 255, 0.18), transparent 34%, rgba(255, 79, 216, 0.12) 68%, rgba(255, 176, 46, 0.08)),
        #05070d;
      background-size: 44px 44px, 44px 44px, 100% 100%, auto;
      line-height: 1.45;
      min-height: 100vh;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(90deg, transparent 0, transparent 18%, rgba(0, 229, 255, 0.10) 18%, rgba(0, 229, 255, 0.10) 18.3%, transparent 18.3%),
        linear-gradient(0deg, transparent 0, transparent 72%, rgba(255, 176, 46, 0.10) 72%, rgba(255, 176, 46, 0.10) 72.3%, transparent 72.3%);
      mix-blend-mode: screen;
      opacity: 0.75;
    }
    .wrap {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      position: relative;
    }
    header {
      border-bottom: 1px solid rgba(0, 229, 255, 0.34);
      background: linear-gradient(180deg, rgba(4, 8, 16, 0.98), rgba(5, 7, 13, 0.78));
      box-shadow: 0 18px 48px rgba(0, 229, 255, 0.10);
    }
    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      padding: 30px 0 22px;
    }
    h1 {
      margin: 0;
      font-size: 42px;
      line-height: 1;
      letter-spacing: 0;
      text-transform: uppercase;
      color: #f4feff;
      text-shadow: 0 0 16px rgba(0, 229, 255, 0.72), 0 0 28px rgba(75, 125, 255, 0.42);
    }
    .subtitle {
      margin-top: 8px;
      color: #a8dce8;
      font-size: 14px;
    }
    .meta {
      text-align: right;
      color: #a8dce8;
      font-size: 14px;
      border: 1px solid rgba(0, 229, 255, 0.25);
      border-radius: 8px;
      padding: 10px 12px;
      background: rgba(4, 14, 26, 0.72);
      box-shadow: inset 0 0 18px rgba(0, 229, 255, 0.08);
    }
    .summary-band {
      border-bottom: 1px solid rgba(0, 229, 255, 0.22);
      background: rgba(5, 12, 22, 0.78);
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      padding: 16px 0;
    }
    .metric {
      min-width: 0;
      border: 1px solid rgba(0, 229, 255, 0.24);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 10px 12px;
      background: rgba(8, 18, 31, 0.86);
      box-shadow: 0 0 18px rgba(0, 229, 255, 0.08), inset 0 0 16px rgba(0, 229, 255, 0.05);
    }
    .metric b {
      display: block;
      font-size: 23px;
      line-height: 1.1;
      color: #ffffff;
    }
    .metric span {
      color: var(--muted);
      font-size: 13px;
    }
    main {
      padding: 18px 0 36px;
    }
    .tabbar {
      display: flex;
      gap: 9px;
      overflow-x: auto;
      padding: 8px 0 16px;
      scrollbar-color: rgba(0, 229, 255, 0.45) transparent;
    }
    .tab {
      flex: 0 0 auto;
      border: 1px solid rgba(0, 229, 255, 0.28);
      border-bottom-color: rgba(255, 255, 255, 0.12);
      border-radius: 8px;
      background: rgba(7, 16, 29, 0.90);
      color: #cceff7;
      padding: 10px 13px;
      font: inherit;
      font-size: 14px;
      cursor: pointer;
      box-shadow: inset 0 0 14px rgba(0, 229, 255, 0.04);
      white-space: nowrap;
    }
    .tab:hover,
    .tab:focus-visible {
      color: #ffffff;
      border-color: var(--accent);
      outline: none;
      box-shadow: 0 0 18px rgba(0, 229, 255, 0.20), inset 0 0 16px rgba(0, 229, 255, 0.10);
    }
    .tab[aria-selected="true"] {
      color: #ffffff;
      border-color: var(--accent);
      background: linear-gradient(180deg, rgba(0, 229, 255, 0.18), rgba(9, 16, 28, 0.96));
      box-shadow: 0 0 24px color-mix(in srgb, var(--accent) 36%, transparent), inset 0 -2px 0 var(--accent);
    }
    .tab-panel {
      border: 1px solid rgba(0, 229, 255, 0.24);
      border-radius: 8px;
      background: rgba(4, 10, 19, 0.78);
      box-shadow: 0 0 32px rgba(0, 229, 255, 0.10);
      padding: 16px;
    }
    .tab-panel[hidden] { display: none; }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
      border-bottom: 1px solid rgba(0, 229, 255, 0.24);
      padding-bottom: 10px;
      margin-bottom: 14px;
    }
    h2 {
      margin: 0;
      font-size: 23px;
      letter-spacing: 0;
      color: #ffffff;
      text-shadow: 0 0 14px color-mix(in srgb, var(--accent) 48%, transparent);
    }
    .count {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .news-grid,
    .trend-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .item,
    .trend-card {
      min-width: 0;
      border: 1px solid rgba(0, 229, 255, 0.22);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      background:
        linear-gradient(90deg, color-mix(in srgb, var(--accent) 8%, transparent), transparent 46%),
        var(--panel);
      padding: 10px 14px;
      box-shadow: inset 0 0 22px rgba(255, 255, 255, 0.025), 0 0 18px rgba(0, 229, 255, 0.06);
    }
    .news-photo { margin: 0 0 14px; }
    .news-photo[hidden] { display: none; }
    .news-photo img { display: block; width: 100%; height: 220px; object-fit: contain; background: #05070d; border-radius: 6px; }
    .news-photo figcaption { margin-top: 5px; color: var(--muted); font-size: 11px; }
    .headline { color: inherit; text-decoration: none; }
    .headline:hover { color: var(--accent); text-decoration: underline; }
    .headline:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
    .item h3,
    .trend-card h3 {
      margin: 0 0 6px;
      font-size: 15px;
      line-height: 1.28;
      letter-spacing: 0;
      color: #ffffff;
    }
    .item p,
    .trend-card p {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .item-footer,
    .trend-footer {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      border-top: 1px solid rgba(0, 229, 255, 0.14);
      padding-top: 9px;
    }
    .rank {
      color: var(--accent);
      font-weight: 700;
      text-shadow: 0 0 12px color-mix(in srgb, var(--accent) 56%, transparent);
    }
    .subtopic {
      display: inline-block;
      margin-bottom: 8px;
      color: var(--accent);
      font-size: 12px;
    }
    .trend-block {
      margin-bottom: 18px;
    }
    .trend-block:last-child {
      margin-bottom: 0;
    }
    .trend-block h3 {
      margin: 0 0 10px;
      font-size: 18px;
      color: #ffffff;
      letter-spacing: 0;
    }
    a {
      color: #72edff;
      text-decoration: none;
      overflow-wrap: anywhere;
    }
    a:hover,
    a:focus-visible {
      color: #ffffff;
      text-decoration: underline;
      outline: none;
    }
    .notes {
      border-top: 1px solid rgba(0, 229, 255, 0.22);
      background: rgba(4, 10, 18, 0.92);
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
      border: 1px solid rgba(0, 229, 255, 0.24);
      background: rgba(8, 18, 31, 0.80);
      color: #d9f7ff;
      padding: 4px 8px;
      border-radius: 8px;
      font-size: 12px;
    }
    .warn {
      margin-top: 12px;
      color: #ffd18a;
    }
    @media (max-width: 860px) {
      .topbar,
      .summary-grid,
      .news-grid,
      .trend-grid,
      .radio-player,
      .briefing-grid {
        grid-template-columns: 1fr;
      }
      .meta {
        text-align: left;
      }
      h1 {
        font-size: 30px;
      }
      .tab-panel {
        padding: 12px;
      }
      .item-footer,
      .trend-footer,
      .radio-head,
      .briefing-head,
      .section-head {
        align-items: flex-start;
        flex-direction: column;
      }
      .radio-meta {
        text-align: left;
      }
      .fast-read ol {
        columns: 1;
      }
    }
    """

    panel_styles = []
    for group in topic_groups:
        name = group.get("name", "Tema")
        accent = group.get("accent", "#00e5ff")
        slug = slug_id(name)
        panel_styles.append(f"#tab-{slug}, #panel-{slug} {{ --accent: {accent}; }}")
    panel_styles.append("#tab-trends, #panel-trends { --accent: #ff4fd8; }")

    tabs = []
    panels = []
    for idx, group in enumerate(topic_groups):
        name = group.get("name", "Tema")
        slug = slug_id(name)
        items = article_groups.get(name, [])[: int(group.get("target", ITEMS_PER_GROUP))]
        selected = "true" if idx == 0 else "false"
        hidden = "" if idx == 0 else " hidden"
        tabs.append(
            f'<button class="tab" id="tab-{slug}" role="tab" aria-selected="{selected}" '
            f'aria-controls="panel-{slug}" data-tab="{slug}">{html.escape(name)}</button>'
        )

        cards = []
        for number, article in enumerate(items, start=1):
            title = html.escape(article.title)
            summary = html.escape(make_summary(article, name))
            subtopic = html.escape(article.category)
            source = html.escape(article.source or "Fuente no indicada")
            published = html.escape(format_date(article.published))
            link = html.escape(article.link)
            if article.link:
                source_html = f'<a href="{link}" target="_blank" rel="noopener">{source}</a>'
            else:
                source_html = source
            picture = ""
            if re.fullmatch(r"images/[a-f0-9]{24}\.(jpg|png|gif|webp)", article.image_url or ""):
                image_src = html.escape(article.image_url, quote=True)
                picture = f'''<figure class="news-photo"><a href="{link}" target="_blank" rel="noopener noreferrer"><img src="{image_src}" alt="Imagen publicada por {source}: {title}" width="800" height="450" loading="lazy" decoding="async" onerror="this.closest('figure').hidden=true"></a><figcaption>Imagen de {source}</figcaption></figure>'''
            title_html = f'<a class="headline" href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>' if article.link else title
            cards.append(
                f"""
                <article class="item">
                  {picture}
                  <span class="subtopic">{subtopic}</span>
                  <h3><span class="rank">{number:02d}</span> {title_html}</h3>
                  <p>{summary}</p>
                  <div class="item-footer">
                    <span>{published}</span>
                    <span>{source_html}</span>
                  </div>
                </article>
                """
            )

        panels.append(
            f"""
            <section class="tab-panel" id="panel-{slug}" role="tabpanel" aria-labelledby="tab-{slug}"{hidden}>
              <div class="section-head">
                <h2>{html.escape(name)}</h2>
                <span class="count">{sum(is_real_article(a) for a in items)} noticias · {sum(not is_real_article(a) for a in items)} espacios pendientes</span>
              </div>
              <p class="subtitle">{html.escape(group.get('description', ''))}</p>
              <div class="news-grid">
                {''.join(cards)}
              </div>
            </section>
            """
        )

    tabs.append(
        '<button class="tab" id="tab-trends" role="tab" aria-selected="false" '
        'aria-controls="panel-trends" data-tab="trends">Trends</button>'
    )

    trend_blocks = []
    for trend_group in trend_groups:
        name = trend_group.get("name", "Trends")
        target = int(trend_group.get("target", TREND_ITEMS_PER_GROUP))
        items = trends.get(name, [])[:target]
        if len(items) < target:
            items = items + fallback_trend_items(name, target - len(items))
        accent = trend_group.get("accent", "#ff4fd8")
        trend_cards = []
        for number, item in enumerate(items, start=1):
            title = html.escape(item.title)
            description = html.escape(shorten_chars(item.description or "Senal de tendencia detectada.", 220))
            source = html.escape(item.source or "Fuente no indicada")
            published = html.escape(format_date(item.published))
            link = html.escape(item.link)
            if item.link:
                source_html = f'<a href="{link}" target="_blank" rel="noopener">{source}</a>'
            else:
                source_html = source
            trend_cards.append(
                f"""
                <article class="trend-card">
                  <h3><span class="rank">#{number:02d}</span> {title}</h3>
                  <p>{description}</p>
                  <div class="trend-footer">
                    <span>{published}</span>
                    <span>{source_html}</span>
                  </div>
                </article>
                """
            )
        trend_blocks.append(
            f"""
            <section class="trend-block" style="--accent: {html.escape(accent)};">
              <h3>{html.escape(name)}</h3>
              <div class="trend-grid">{''.join(trend_cards)}</div>
            </section>
            """
        )

    panels.append(
        f"""
        <section class="tab-panel" id="panel-trends" role="tabpanel" aria-labelledby="tab-trends" hidden>
          <div class="section-head">
            <h2>Trends</h2>
            <span class="count">{sum(len(items) for items in trends.values()) or TREND_ITEMS_PER_GROUP * len(trend_groups)} senales</span>
          </div>
          {''.join(trend_blocks)}
        </section>
        """
    )

    chips = "".join(f'<span class="chip">{html.escape(item)}</span>' for item in detected)
    error_html = ""
    if errors:
        sample = "; ".join(errors[:6])
        error_html = f'<p class="warn">Avisos RSS: {html.escape(shorten_chars(sample, 520))}</p>'

    script = """
    <script>
    (function () {
      var tabs = Array.prototype.slice.call(document.querySelectorAll("[data-tab]"));
      var panels = Array.prototype.slice.call(document.querySelectorAll("[role='tabpanel']"));
      function activate(id) {
        tabs.forEach(function (tab) {
          var active = tab.getAttribute("data-tab") === id;
          tab.setAttribute("aria-selected", active ? "true" : "false");
        });
        panels.forEach(function (panel) {
          panel.hidden = panel.id !== "panel-" + id;
        });
      }
      tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
          activate(tab.getAttribute("data-tab"));
        });
      });
    }());
    </script>
    """

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{AGENT_NAME} - Noticias del día</title>
  <style>{style}{''.join(panel_styles)}</style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>{AGENT_NAME}</h1>
        <div class="subtitle">Tu noticiario diario · Argentina, tecnología, agro y noticias de la zona</div>
      </div>
      <div class="meta">
        <div>{generated.strftime("%A %d/%m/%Y")}</div>
        <div>Generado {generated.strftime("%H:%M")}</div>
      </div>
    </div>
  </header>
  <div class="summary-band">
    <div class="wrap summary-grid">
      <div class="metric"><b>{sum(is_real_article(a) for a in articles)}</b><span>noticias seleccionadas</span></div>
      <div class="metric" style="--accent:#ff4fd8;"><b>{len(topic_groups)}</b><span>secciones</span></div>
      <div class="metric" style="--accent:#22f2a6;"><b>{sum(bool(a.image_url) for a in articles)}</b><span>noticias con imagen</span></div>
      <div class="metric"><b>{trend_count or TREND_ITEMS_PER_GROUP * len(trend_groups)}</b><span>trends monitoreados</span></div>
    </div>
  </div>
  <main class="wrap">
    <nav class="tabbar" role="tablist" aria-label="Solapas de Agent News">
      {''.join(tabs)}
    </nav>
    {''.join(panels)}
  </main>
  <footer class="notes">
    <div class="wrap">
      <strong>Tematicas configuradas:</strong>
      <div class="chips">{chips}</div>
      <p>{html.escape(profile.get("privacy", ""))}</p>
      {error_html}
    </div>
  </footer>
  {script}
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
    themes_by_name = {theme.get("name", "Tema"): theme for theme in profile_themes(profile)}
    for group in profile_topic_groups(profile):
        group_name = group.get("name", "Tema")
        target = int(group.get("target", ITEMS_PER_GROUP))
        categories = group.get("categories", [group_name])
        for idx in range(target):
            category = categories[idx % len(categories)]
            theme = themes_by_name.get(category, {})
            queries = theme.get("queries", [category])
            demo.append(
                Article(
                    category=category,
                    query=queries[idx % len(queries)],
                    title=f"Ejemplo {idx + 1} para {group_name}",
                    link="https://news.google.com/",
                    source="Demo local",
                    description=(
                        "Resumen de prueba para validar solapas, estetica futurista, limite de "
                        "500 caracteres y agrupacion por problematica central."
                    ),
                    published=today,
                )
            )
    return demo


def offline_demo_trends(profile: dict) -> dict[str, list[TrendItem]]:
    today = now_local()
    demo: dict[str, list[TrendItem]] = {}
    for group in profile_trend_groups(profile):
        name = group.get("name", "Trends")
        target = int(group.get("target", TREND_ITEMS_PER_GROUP))
        demo[name] = [
            TrendItem(
                group=name,
                title=f"{name} trend #{index + 1}",
                link="https://trends.google.com/",
                source="Demo local",
                description="Senal de tendencia de prueba para validar la solapa Trends sin usar internet.",
                published=today,
                score=1.0,
            )
            for index in range(target)
        ]
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
        trends = offline_demo_trends(profile)
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
        trends, trend_errors = collect_trends(profile)
        errors.extend(trend_errors)

    if not args.offline_demo:
        image_errors = enrich_images(articles, OUTPUT_DIR)
        image_count = sum(bool(article.image_url) for article in articles)
        log(f"Publisher photos: {image_count}/{sum(is_real_article(a) for a in articles)}; unavailable: {len(image_errors)}")
        for image_error in image_errors:
            log(f"Image unavailable: {image_error}")
    html_text = render_html(articles, profile, errors, trends)
    report_path = write_report(html_text)
    elapsed = time.time() - start
    log(f"Report generated: {report_path} in {elapsed:.1f}s with {len(articles)} items")

    if not args.no_open:
        open_report(report_path)
    print(str(report_path))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent News: noticias diarias con imágenes.")
    parser.add_argument("--no-open", action="store_true", help="Generate the report without opening it.")
    parser.add_argument("--no-audio", action="store_true", help=argparse.SUPPRESS)
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
