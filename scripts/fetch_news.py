#!/usr/bin/env python3
"""
Fetches news from RSS feeds, sorts into categories, geocodes mentioned
locations (countries AND cities) with a static lookup table, detects
event types (conflict / disaster / tension / trade) for map styling,
finds connections between locations for arcs (trade routes, conflict
fronts), and writes news.json for the dashboard frontend to consume.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape

USER_AGENT = "Mozilla/5.0 (compatible; MorningNewsDashboard/1.0)"


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rss(xml_text: str):
    """Minimal RSS2.0 parser using stdlib only (no feedparser dependency)."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    feed_title = channel.findtext("title", default="") if channel is not None else ""
    entries = []
    for item in (channel.findall("item") if channel is not None else []):
        entries.append({
            "title": item.findtext("title", default=""),
            "link": item.findtext("link", default=""),
            "summary": item.findtext("description", default=""),
            "published": item.findtext("pubDate", default=""),
        })
    return feed_title, entries

# ---------------------------------------------------------------------------
# Category configuration - EASY TO EXTEND: just add a new entry here with a
# label, color, and one or more RSS feed URLs. Optional "keywords" filters
# items pulled from a shared feed (e.g. splitting "Ausland" into conflicts
# vs. general world news).
# ---------------------------------------------------------------------------
CATEGORIES = [
    {
        "id": "politik",
        "label": "Politik",
        "color": "#5b9bd5",
        "feeds": ["https://www.tagesschau.de/inland/index~rss2.xml"],
    },
    {
        "id": "wirtschaft",
        "label": "Wirtschaft",
        "color": "#4caf50",
        "feeds": ["https://www.tagesschau.de/wirtschaft/index~rss2.xml"],
    },
    {
        "id": "konflikte",
        "label": "Kriege & Konflikte",
        "color": "#e74c3c",
        "feeds": ["https://www.tagesschau.de/ausland/index~rss2.xml"],
        "keywords": [
            "krieg", "konflikt", "angriff", "militär", "truppen", "offensive",
            "waffen", "front", "besetz", "invasion", "luftangriff", "rakete",
            "kämpfe", "gefecht", "bombardier", "geisel", "waffenruhe",
        ],
    },
    {
        "id": "welt",
        "label": "Weltgeschehen",
        "color": "#f39c12",
        "feeds": ["https://www.tagesschau.de/ausland/index~rss2.xml"],
        "exclude_keywords": [
            "krieg", "konflikt", "angriff", "militär", "truppen", "offensive",
            "waffen", "front", "besetz", "invasion", "luftangriff", "rakete",
            "kämpfe", "gefecht", "bombardier", "geisel", "waffenruhe",
        ],
    },
    {
        "id": "sport",
        "label": "Sport",
        "color": "#9b59b6",
        "feeds": ["https://www.tagesschau.de/sport/index~rss2.xml"],
    },
]

MAX_PER_CATEGORY = 8

# ---------------------------------------------------------------------------
# Event-type detection - drives how a marker is drawn on the map (pulsing
# ring color, dome color, whether it gets a connecting arc).
# ---------------------------------------------------------------------------
DISASTER_KEYWORDS = [
    "erdbeben", "überschwemmung", "flut", "hochwasser", "hurrikan", "taifun",
    "wirbelsturm", "dürre", "waldbrand", "waldbrände", "vulkan", "tsunami",
    "hitzewelle", "erdrutsch", "unwetter", "sturmflut", "erdrutsche",
]
TENSION_KEYWORDS = [
    "spannungen", "spannung", "krise", "drohung", "gedroht", "sanktionen",
    "eskalation", "eskaliert", "streit", "provokation", "warnung",
]
TRADE_KEYWORDS = [
    "handel", "handelsabkommen", "export", "import", "zoll", "zölle",
    "freihandelsabkommen", "lieferkette", "abkommen", "deal", "investition",
    "exporte", "importe",
]

EVENT_COLORS = {
    "conflict": "#ff3b30",
    "disaster": "#ff9500",
    "tension": "#ffd60a",
    "trade": "#34c759",
    "standard": None,  # falls back to category color
}

# ---------------------------------------------------------------------------
# Static place -> coordinates lookup for map markers. Covers countries AND
# major cities so events can be pinned precisely instead of just to a
# country's center. Matched case-insensitively as whole words against
# title + summary. Longer names are matched first (e.g. "Südkorea" before
# "Korea") via the sorted pattern below.
# ---------------------------------------------------------------------------
PLACES = {
    # Countries (fallback centers)
    "Deutschland": (51.1657, 10.4515),
    "Ukraine": (48.3794, 31.1656),
    "Russland": (61.5240, 105.3188),
    "USA": (37.0902, -95.7129),
    "China": (35.8617, 104.1954),
    "Israel": (31.0461, 34.8516),
    "Iran": (32.4279, 53.688),
    "Frankreich": (46.2276, 2.2137),
    "Großbritannien": (55.3781, -3.436),
    "Indien": (20.5937, 78.9629),
    "Brasilien": (-14.235, -51.9253),
    "Japan": (36.2048, 138.2529),
    "Südkorea": (35.9078, 127.7669),
    "Nordkorea": (40.3399, 127.5101),
    "Syrien": (34.8021, 38.9968),
    "Türkei": (38.9637, 35.2433),
    "Ägypten": (26.8206, 30.8025),
    "Saudi-Arabien": (23.8859, 45.0792),
    "Libanon": (33.8547, 35.8623),
    "Jemen": (15.5527, 48.5164),
    "Sudan": (12.8628, 30.2176),
    "Äthiopien": (9.145, 40.4897),
    "Nigeria": (9.082, 8.6753),
    "Südafrika": (-30.5595, 22.9375),
    "Kanada": (56.1304, -106.3468),
    "Mexiko": (23.6345, -102.5528),
    "Italien": (41.8719, 12.5674),
    "Spanien": (40.4637, -3.7492),
    "Polen": (51.9194, 19.1451),
    "Österreich": (47.5162, 14.5501),
    "Schweiz": (46.8182, 8.2275),
    "Niederlande": (52.1326, 5.2913),
    "Schweden": (60.1282, 18.6435),
    "Griechenland": (39.0742, 21.8243),
    "Taiwan": (23.6978, 120.9605),
    "Venezuela": (6.4238, -66.5897),
    "Argentinien": (-38.4161, -63.6167),
    "Australien": (-25.2744, 133.7751),
    "Belgien": (50.5039, 4.4699),
    "Pakistan": (30.3753, 69.3451),
    "Afghanistan": (33.9391, 67.71),
    "Irak": (33.2232, 43.6793),
    "Georgien": (42.3154, 43.3569),
    "Weißrussland": (53.7098, 27.9534),
    "Portugal": (39.3999, -8.2245),
    "Ungarn": (47.1625, 19.5033),
    "Tschechien": (49.8175, 15.473),
    "Dänemark": (56.2639, 9.5018),
    "Finnland": (61.9241, 25.7482),
    "Norwegen": (60.472, 8.4689),
    "Indonesien": (-0.7893, 113.9213),
    "Thailand": (15.87, 100.9925),
    "Vietnam": (14.0583, 108.2772),
    "Malaysia": (4.2105, 101.9758),
    "Philippinen": (12.8797, 121.774),
    "Kolumbien": (4.5709, -74.2973),
    "Chile": (-35.6751, -71.543),
    "Peru": (-9.19, -75.0152),
    "Kenia": (-0.0236, 37.9062),
    "Marokko": (31.7917, -7.0926),
    "Algerien": (28.0339, 1.6596),
    "Libyen": (26.3351, 17.2283),
    "Somalia": (5.1521, 46.1996),

    # Cities
    "Berlin": (52.52, 13.405), "München": (48.1351, 11.582),
    "Frankfurt": (50.1109, 8.6821), "Hamburg": (53.5511, 9.9937),
    "Köln": (50.9375, 6.9603), "Stuttgart": (48.7758, 9.1829),
    "Kiew": (50.4501, 30.5234), "Charkiw": (49.9935, 36.2304),
    "Odessa": (46.4825, 30.7233), "Mariupol": (47.0971, 37.5434),
    "Moskau": (55.7558, 37.6173), "Sankt Petersburg": (59.9311, 30.3609),
    "Washington": (38.9072, -77.0369), "New York": (40.7128, -74.006),
    "Los Angeles": (34.0522, -118.2437), "Chicago": (41.8781, -87.6298),
    "Peking": (39.9042, 116.4074), "Shanghai": (31.2304, 121.4737),
    "Tel Aviv": (32.0853, 34.7818), "Jerusalem": (31.7683, 35.2137),
    "Gaza": (31.5, 34.47), "Ramallah": (31.9038, 35.2034),
    "Teheran": (35.6892, 51.389), "Paris": (48.8566, 2.3522),
    "London": (51.5072, -0.1276), "Neu-Delhi": (28.6139, 77.209),
    "Mumbai": (19.076, 72.8777), "Rio de Janeiro": (-22.9068, -43.1729),
    "São Paulo": (-23.5505, -46.6333), "Tokio": (35.6762, 139.6503),
    "Seoul": (37.5665, 126.978), "Pjöngjang": (39.0392, 125.7625),
    "Damaskus": (33.5138, 36.2765), "Aleppo": (36.2021, 37.1343),
    "Ankara": (39.9334, 32.8597), "Istanbul": (41.0082, 28.9784),
    "Kairo": (30.0444, 31.2357), "Riad": (24.7136, 46.6753),
    "Dubai": (25.2048, 55.2708), "Beirut": (33.8938, 35.5018),
    "Sanaa": (15.3694, 44.191), "Khartum": (15.5007, 32.5599),
    "Addis Abeba": (9.03, 38.74), "Lagos": (6.5244, 3.3792),
    "Johannesburg": (-26.2041, 28.0473), "Kapstadt": (-33.9249, 18.4241),
    "Nairobi": (-1.2921, 36.8219), "Ottawa": (45.4215, -75.6972),
    "Mexiko-Stadt": (19.4326, -99.1332), "Rom": (41.9028, 12.4964),
    "Madrid": (40.4168, -3.7038), "Lissabon": (38.7223, -9.1393),
    "Wien": (48.2082, 16.3738), "Zürich": (47.3769, 8.5417),
    "Amsterdam": (52.3676, 4.9041), "Brüssel": (50.8503, 4.3517),
    "Kopenhagen": (55.6761, 12.5683), "Stockholm": (59.3293, 18.0686),
    "Oslo": (59.9139, 10.7522), "Helsinki": (60.1699, 24.9384),
    "Warschau": (52.2297, 21.0122), "Prag": (50.0755, 14.4378),
    "Budapest": (47.4979, 19.0402), "Bukarest": (44.4268, 26.1025),
    "Sofia": (42.6977, 23.3219), "Belgrad": (44.7866, 20.4489),
    "Sarajevo": (43.8563, 18.4131), "Amman": (31.9454, 35.9284),
    "Buenos Aires": (-34.6037, -58.3816), "Caracas": (10.4806, -66.9036),
    "Sydney": (-33.8688, 151.2093), "Melbourne": (-37.8136, 144.9631),
    "Bangkok": (13.7563, 100.5018), "Jakarta": (-6.2088, 106.8456),
    "Manila": (14.5995, 120.9842), "Hanoi": (21.0278, 105.8342),
    "Singapur": (1.3521, 103.8198), "Kuala Lumpur": (3.139, 101.6869),
    "Genf": (46.2044, 6.1432), "Straßburg": (48.5734, 7.7521),
    "Den Haag": (52.0705, 4.3007),
}
PLACE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in sorted(PLACES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_PLACE_LOOKUP_LOWER = {k.lower(): (k, v) for k, v in PLACES.items()}

DEFAULT_LOCATION = (51.1657, 10.4515)  # Deutschland as fallback center


def strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def find_all_locations(text: str, limit: int = 4):
    """Return up to `limit` distinct places mentioned in text, in order of
    first appearance."""
    seen = []
    for match in PLACE_PATTERN.finditer(text):
        name, coords = _PLACE_LOOKUP_LOWER[match.group(1).lower()]
        if name not in [s["name"] for s in seen]:
            seen.append({"name": name, "lat": coords[0], "lon": coords[1]})
        if len(seen) >= limit:
            break
    return seen


def matches_keywords(text: str, keywords) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def detect_event_type(category_id: str, text: str) -> str:
    if category_id == "konflikte":
        return "conflict"
    if category_id == "welt" and matches_keywords(text, DISASTER_KEYWORDS):
        return "disaster"
    if category_id == "wirtschaft" and matches_keywords(text, TRADE_KEYWORDS):
        return "trade"
    if category_id in ("politik", "welt") and matches_keywords(text, TENSION_KEYWORDS):
        return "tension"
    return "standard"


def fetch_category(cat):
    seen_links = set()
    items = []
    for feed_url in cat["feeds"]:
        xml_text = fetch_url(feed_url)
        feed_title, entries = parse_rss(xml_text)
        for entry in entries:
            link = entry.get("link")
            if not link or link in seen_links:
                continue
            title = strip_html(entry.get("title", ""))
            summary = strip_html(entry.get("summary", ""))
            haystack = f"{title} {summary}"

            if cat.get("keywords") and not matches_keywords(haystack, cat["keywords"]):
                continue
            if cat.get("exclude_keywords") and matches_keywords(haystack, cat["exclude_keywords"]):
                continue

            seen_links.add(link)
            published = entry.get("published", "")

            locations = find_all_locations(haystack)
            primary_location = locations[0] if locations else {
                "name": None, "lat": DEFAULT_LOCATION[0], "lon": DEFAULT_LOCATION[1],
            }

            event_type = detect_event_type(cat["id"], haystack)

            # Connections (arcs) only make sense for conflict fronts and
            # trade routes, and only when we actually found 2+ distinct places.
            connections = []
            if event_type in ("conflict", "trade") and len(locations) >= 2:
                connections.append({
                    "from": locations[0],
                    "to": locations[1],
                })

            items.append({
                "title": title,
                "summary": summary[:280],
                "source": feed_title or "Tagesschau",
                "url": link,
                "category": cat["id"],
                "event_type": event_type,
                "location": primary_location,
                "connections": connections,
                "published": published,
            })
            if len(items) >= MAX_PER_CATEGORY:
                break
    return items


def main():
    articles = []
    for cat in CATEGORIES:
        try:
            articles.extend(fetch_category(cat))
        except Exception as exc:  # keep going even if one feed fails
            print(f"Warning: failed to fetch category {cat['id']}: {exc}", file=sys.stderr)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "categories": [
            {"id": c["id"], "label": c["label"], "color": c["color"]} for c in CATEGORIES
        ],
        "event_colors": EVENT_COLORS,
        "articles": articles,
    }

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(articles)} articles to news.json")


if __name__ == "__main__":
    main()
