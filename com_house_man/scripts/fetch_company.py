#!/usr/bin/env python3
"""Fetch Companies House profile, charges, and PSC data for a company number."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.company-information.service.gov.uk"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_api_key():
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    if not api_key:
        print("Error: COMPANIES_HOUSE_API_KEY is not set in .env", file=sys.stderr)
        sys.exit(1)
    return api_key


def normalize_company_number(value):
    return (value or "").strip().zfill(8)


def request_json(session, endpoint):
    url = f"{BASE_URL}{endpoint}"
    response = session.get(url, timeout=30)

    if response.status_code == 429:
        print("Rate limited — waiting 60s and retrying...", file=sys.stderr)
        time.sleep(60)
        response = session.get(url, timeout=30)

    response.raise_for_status()
    return response.json()


def fetch_company_data(company_number):
    api_key = load_api_key()
    company_number = normalize_company_number(company_number)

    session = requests.Session()
    session.auth = (api_key, "")

    profile = request_json(session, f"/company/{company_number}")
    charges = request_json(session, f"/company/{company_number}/charges")
    pscs = request_json(
        session,
        f"/company/{company_number}/persons-with-significant-control",
    )

    return {
        "company_number": company_number,
        "profile": profile,
        "charges": charges,
        "persons_with_significant_control": pscs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Companies House data for a company number."
    )
    parser.add_argument("company_number", help="Company number (e.g. 12345678)")
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to write JSON output (prints to stdout if omitted)",
    )
    args = parser.parse_args()

    try:
        data = fetch_company_data(args.company_number)
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(data, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output, encoding="utf-8")
        print(f"Wrote {output_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
