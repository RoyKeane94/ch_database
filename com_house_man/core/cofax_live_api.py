import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import feedparser
import requests
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from core.models import Company

log = logging.getLogger(__name__)

CACHE_KEY = "cofax_live_v3"
CACHE_SECONDS = 600

LAT, LON = 51.46, -0.30
BBC_FEED = "https://feeds.bbci.co.uk/news/business/rss.xml"
BBC_FOOTBALL_FEED = "https://feeds.bbci.co.uk/sport/football/rss.xml"
TFL_STATUS_URL = "https://api.tfl.gov.uk/Line/Mode/tube,overground/Status"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
WIKIPEDIA_ON_THIS_DAY = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events"

TFL_DISTRICT_FALLBACK = {
    "tag": "DISTRICT",
    "text": "SORRY, WE'RE NOT QUITE SURE. LET US SPEAK TO SADIQ",
    "page": "430",
    "url": "https://tfl.gov.uk/tube/status/#district-line",
}
TFL_LINES = [
    "district",
    "overground",
    "piccadilly",
    "central",
    "northern",
    "jubilee",
    "victoria",
    "circle",
    "bakerloo",
    "metropolitan",
    "elizabeth",
]
TFL_LINE_PAGE = {
    "district": "430",
    "overground": "431",
    "piccadilly": "432",
    "central": "433",
    "northern": "434",
    "jubilee": "435",
    "victoria": "436",
    "circle": "437",
    "bakerloo": "438",
    "metropolitan": "439",
    "elizabeth": "440",
}
BBC_WEATHER_URL = "https://www.bbc.co.uk/weather/2647428"

WMO = {
    0: "CLEAR SKIES",
    1: "MAINLY CLEAR",
    2: "SUNNY INTERVALS",
    3: "OVERCAST",
    45: "FOG",
    48: "FREEZING FOG",
    51: "LIGHT DRIZZLE",
    53: "DRIZZLE",
    55: "HEAVY DRIZZLE",
    61: "LIGHT RAIN",
    63: "RAIN",
    65: "HEAVY RAIN",
    71: "LIGHT SNOW",
    73: "SNOW",
    75: "HEAVY SNOW",
    80: "SHOWERS",
    81: "HEAVY SHOWERS",
    82: "VIOLENT SHOWERS",
    95: "THUNDERSTORMS",
    96: "THUNDER + HAIL",
    99: "SEVERE THUNDER",
}


def _register_stats():
    total = Company.objects.count()
    active = Company.objects.filter(company_status__icontains="active").count()
    week_ago = date.today() - timedelta(days=7)
    new_this_week = Company.objects.filter(date_of_creation__gte=week_ago).count()
    if new_this_week == 0:
        new_this_week = Company.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count()
    synced = Company.objects.filter(
        needs_enrichment=False,
        last_fetched_at__isnull=False,
    ).count()
    return {
        "total": f"{total:,}",
        "active": f"{active:,}",
        "new_this_week": str(new_this_week),
        "synced": str(synced),
    }


def _ticker(stats):
    return (
        f"KEY 101 TO SEARCH THE REGISTER +++ "
        f"{stats['total']} COMPANIES ON FILE +++ "
        f"{stats['synced']} SYNCED FROM API +++ "
        f"{stats['new_this_week']} NEW THIS WEEK +++"
    )


def _truncate_teletext(text, limit=46):
    text = (text or "").upper().strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _weather():
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT,
            "longitude": LON,
            "current": "temperature_2m,weather_code",
        },
        timeout=4,
    )
    response.raise_for_status()
    current = response.json()["current"]
    temp = round(current["temperature_2m"])
    desc = WMO.get(current["weather_code"], "CHANGEABLE")
    return {
        "text": f"RICHMOND {temp}C — {desc}",
        "page": "401",
        "url": BBC_WEATHER_URL,
    }


def _headline():
    feed = feedparser.parse(BBC_FEED)
    if not feed.entries:
        raise ValueError("empty feed")
    entry = feed.entries[0]
    title = entry.title.upper()
    return {
        "text": _truncate_teletext(title),
        "page": "201",
        "url": entry.get("link", "https://www.bbc.co.uk/news/business"),
    }


def _ftse():
    try:
        response = requests.get(
            "https://stooq.com/q/l/",
            params={"s": "^ftse", "f": "sd2t2ohlcv", "h": "", "e": "csv"},
            timeout=4,
        )
        response.raise_for_status()
        row = response.text.strip().splitlines()[1].split(",")
        open_price, close = float(row[3]), float(row[6])
        change = round((close - open_price) / open_price * 100, 1)
        return {"value": f"{close:,.0f}", "change": change, "page": "220"}
    except Exception:
        log.info("Stooq failed, trying Yahoo")

    response = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EFTSE",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=4,
    )
    response.raise_for_status()
    meta = response.json()["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev = meta["chartPreviousClose"]
    change = round((price - prev) / prev * 100, 1)
    return {"value": f"{price:,.0f}", "change": change, "page": "220"}


def _tfl_lines():
    response = requests.get(TFL_STATUS_URL, timeout=4)
    response.raise_for_status()
    by_id = {line.get("id"): line for line in response.json()}
    rows = []
    for line_id in TFL_LINES:
        line = by_id.get(line_id)
        if not line:
            if line_id == "district":
                rows.append(dict(TFL_DISTRICT_FALLBACK))
            continue
        name = line.get("name", line_id).upper()
        if not name.endswith("LINE"):
            name = f"{name} LINE"
        status = line["lineStatuses"][0]["statusSeverityDescription"].upper()
        rows.append(
            {
                "tag": line.get("name", line_id).upper()[:10],
                "text": f"{name}: {status}",
                "page": TFL_LINE_PAGE.get(line_id, "430"),
                "url": f"https://tfl.gov.uk/tube/status/#{line_id}-line",
            }
        )
    if not rows:
        return [dict(TFL_DISTRICT_FALLBACK)]
    return rows


def _currency():
    response = requests.get(
        FRANKFURTER_URL,
        params={"base": "GBP", "symbols": "USD,EUR"},
        timeout=4,
    )
    response.raise_for_status()
    rates = response.json()["rates"]
    usd = rates["USD"]
    eur = rates["EUR"]
    return {
        "text": f"£1 = ${usd:.2f} / €{eur:.2f}",
        "page": "240",
    }


def _football():
    feed = feedparser.parse(BBC_FOOTBALL_FEED)
    if not feed.entries:
        raise ValueError("empty football feed")
    entry = feed.entries[0]
    title = entry.title.upper()
    return {
        "text": _truncate_teletext(title),
        "page": "302",
        "url": entry.get("link", "https://www.bbc.co.uk/sport/football"),
    }


def _on_this_day():
    today = date.today()
    url = f"{WIKIPEDIA_ON_THIS_DAY}/{today.month:02d}/{today.day:02d}"
    response = requests.get(
        url,
        headers={"User-Agent": "COFAX/1.0 (companies register teletext)"},
        timeout=4,
    )
    response.raise_for_status()
    events = response.json().get("events") or []
    if not events:
        raise ValueError("no on-this-day events")
    event = events[0]
    year = event.get("year", "")
    text = event.get("text", "").replace("<", "").replace(">", "")
    text = " ".join(text.split())
    article_url = f"https://en.wikipedia.org/wiki/On_this_day_{today.strftime('%B')}_{today.day}"
    pages = event.get("pages") or []
    if pages:
        content_urls = pages[0].get("content_urls") or {}
        article_url = (
            content_urls.get("desktop", {}).get("page")
            or content_urls.get("mobile", {}).get("page")
            or article_url
        )
    return {
        "text": _truncate_teletext(f"{year}: {text}"),
        "page": "455",
        "url": article_url,
    }


def cofax_live(request):
    cached = cache.get(CACHE_KEY)
    if cached:
        return JsonResponse(cached)

    stats = _register_stats()
    data = {
        "stats": stats,
        "ticker": _ticker(stats),
    }
    fetchers = (
        ("weather", _weather),
        ("headline", _headline),
        ("ftse", _ftse),
        ("tfl_lines", _tfl_lines),
        ("currency", _currency),
        ("football", _football),
        ("on_this_day", _on_this_day),
    )
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = {pool.submit(fn): key for key, fn in fetchers}
        for future in as_completed(futures):
            key = futures[future]
            try:
                data[key] = future.result()
            except Exception:
                log.exception("COFAX %s fetch failed", key)
                if key == "tfl_lines":
                    data[key] = [TFL_DISTRICT_FALLBACK]

    cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return JsonResponse(data)
