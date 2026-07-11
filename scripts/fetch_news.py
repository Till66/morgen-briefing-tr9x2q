#!/usr/bin/env python3
"""
Fetches news from RSS feeds, sorts into categories, geocodes mentioned
locations with a static lookup table, and writes news.json for the
dashboard frontend to consume.
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
# Static place -> coordinates lookup for globe markers. Matched
# case-insensitively as whole words against title + summary.
# ---------------------------------------------------------------------------
PLACES = {
    "Deutschland": (51.1657, 10.4515), "Berlin": (52.52, 13.405),
    "München": (48.1351, 11.582), "Frankfurt": (50.1109, 8.6821),
    "Ukraine": (48.3794, 31.1656), "Kiew": (50.4501, 30.5234),
    "Russland": (61.5240, 105.3188), "Moskau": (55.7558, 37.6173),
    "USA": (37.0902, -95.7129), "Washington": (38.9072, -77.0369),
    "China": (35.8617, 104.1954), "Peking": (39.9042, 116.4074),
    "Israel": (31.0461, 34.8516), "Gaza": (31.5, 34.47),
    "Iran": (32.4279, 53.688), "Teheran": (35.6892, 51.389),
    "Frankreich": (46.2276, 2.2137), "Paris": (48.8566, 2.3522),
    "Großbritannien": (55.3781, -3.436), "London": (51.5072, -0.1276),
    "Indien": (20.5937, 78.9629), "Brasilien": (-14.235, -51.9253),
    "Japan": (36.2048, 138.2529), "Südkorea": (35.9078, 127.7669),
    "Nordkorea": (40.3399, 127.5101), "Syrien": (34.8021, 38.9968),
    "Türkei": (38.9637, 35.2433), "Ägypten": (26.8206, 30.8025),
    "Saudi-Arabien": (23.8859, 45.0792), "Libanon": (33.8547, 35.8623),
    "Jemen": (15.5527, 48.5164), "Sudan": (12.8628, 30.2176),
    "Äthiopien": (9.145, 40.4897), "Nigeria": (9.082, 8.6753),
    "Südafrika": (-30.5595, 22.9375), "Kanada": (56.1304, -106.3468),
    "Mexiko": (23.6345, -102.5528), "Italien": (41.8719, 12.5674),
    "Spanien": (40.4637, -3.7492), "Polen": (51.9194, 19.1451),
    "Österreich": (47.5162, 14.5501), "Schweiz": (46.8182, 8.2275),
    "Niederlande": (52.1326, 5.2913), "Schweden": (60.1282, 18.6435),
    "Griechenland": (39.0742, 21.8243), "Taiwan": (23.6978, 120.9605),
    "Venezuela": (6.4238, -66.5897), "Argentinien": (-38.4161, -63.6167),
    "Australien": (-25.2744, 133.7751), "Belgien": (50.5039, 4.4699),
    "Brüssel": (50.8503, 4.3517), "Pakistan": (30.3753, 69.3451),
    "Afghanistan": (33.9391, 67.71), "Irak": (33.2232, 43.6793),
    "Georgien": (42.3154, 43.3569), "Weißrussland": (53.7098, 27.9534),
    "Portugal": (39.3999, -8.2245), "Ungarn": (47.1625, 19.5033),
    "Tschechien": (49.8175, 15.473), "Dänemark": (56.2639, 9.5018),
    "Finnland": (61.9241, 25.7482), "Norwegen": (60.472, 8.4689),
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


def find_location(text: str):
    match = PLACE_PATTERN.search(text)
    if not match:
        return None
    name, coords = _PLACE_LOOKUP_LOWER[match.group(1).lower()]
    return {"name": name, "lat": coords[0], "lon": coords[1]}


def matches_keywords(text: str, keywords) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


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

            location = find_location(haystack) or {
                "name": None, "lat": DEFAULT_LOCATION[0], "lon": DEFAULT_LOCATION[1],
            }

            items.append({
                "title": title,
                "summary": summary[:280],
                "source": feed_title or "Tagesschau",
                "url": link,
                "category": cat["id"],
                "location": location,
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
        "articles": articles,
    }

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(articles)} articles to news.json")


if __name__ == "__main__":
    main()
