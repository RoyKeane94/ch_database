import csv
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
SIC_MATCH_LIMIT = 50


def normalize_sic_code(code):
    code = str(code).strip()
    if code.isdigit():
        return code.zfill(5)
    return code


@lru_cache(maxsize=1)
def _load_condensed():
    codes = {}
    path = DATA_DIR / "condensed_sic_codes.csv"
    with path.open(encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) >= 2 and row[0].strip():
                code = normalize_sic_code(row[0])
                codes[code] = row[1].strip()
    return codes


@lru_cache(maxsize=1)
def _load_activity_index():
    index = {}
    path = DATA_DIR / "ons_economic_activities_alphabetic_index.csv"
    with path.open(encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) >= 2 and row[0].strip():
                code = normalize_sic_code(row[0])
                activity = row[1].strip().lower()
                index.setdefault(code, []).append(activity)
    return index


def sic_description(code):
    return _load_condensed().get(normalize_sic_code(code), "")


def sic_labels(codes):
    return [
        {
            "code": normalize_sic_code(code),
            "description": sic_description(code),
        }
        for code in (codes or [])
        if str(code).strip()
    ]


def find_matching_sic_codes(query, limit=SIC_MATCH_LIMIT):
    query = query.strip().lower()
    if not query:
        return []

    condensed = _load_condensed()
    activities = _load_activity_index()
    matches = []
    seen = set()

    normalized = normalize_sic_code(query)
    if normalized in condensed:
        return [normalized]

    if query.isdigit():
        for code in condensed:
            if code.startswith(query) and code not in seen:
                seen.add(code)
                matches.append(code)
        if matches:
            return sorted(matches)[:limit]

    for code, description in condensed.items():
        if query in description.lower() and code not in seen:
            seen.add(code)
            matches.append(code)

    for code, phrases in activities.items():
        if code in seen:
            continue
        for phrase in phrases:
            if query in phrase:
                seen.add(code)
                matches.append(code)
                break

    return sorted(matches)[:limit]


@lru_cache(maxsize=1)
def all_sic_codes():
    condensed = _load_condensed()
    return tuple(
        {"code": code, "description": description}
        for code, description in sorted(condensed.items())
    )


def sic_search_results(query):
    condensed = _load_condensed()
    return [
        {"code": code, "description": condensed.get(code, "")}
        for code in find_matching_sic_codes(query)
    ]


def company_sic_filter_q(codes):
    from django.db.models import Q

    filter_q = Q()
    for code in codes:
        normalized = normalize_sic_code(code)
        filter_q |= Q(sic_codes__contains=[normalized])
        stripped = normalized.lstrip("0")
        if stripped and stripped != normalized:
            filter_q |= Q(sic_codes__contains=[stripped])
    return filter_q
