import time

import requests
from django.conf import settings


BASE_URL = "https://api.company-information.service.gov.uk"
MIN_REQUEST_INTERVAL = 0.55
RATE_LIMIT_BACKOFF_SECONDS = 60
MAX_RETRIES = 3
ITEMS_PER_PAGE = 100
MAX_LIST_PAGES = 50


class CompaniesHouseClient:
    _last_request_at = 0.0

    def __init__(self, min_interval=MIN_REQUEST_INTERVAL):
        self.auth = (settings.COMPANIES_HOUSE_API_KEY, "")
        self.timeout = 30
        self.min_interval = min_interval

    def _throttle(self):
        elapsed = time.monotonic() - CompaniesHouseClient._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request(self, endpoint, params=None, *, allow_not_found=False):
        url = f"{BASE_URL}{endpoint}"
        response = None

        try:
            for attempt in range(MAX_RETRIES + 1):
                self._throttle()
                response = requests.get(
                    url,
                    auth=self.auth,
                    params=params,
                    timeout=self.timeout,
                )
                CompaniesHouseClient._last_request_at = time.monotonic()

                if response.status_code == 429 and attempt < MAX_RETRIES:
                    time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                    continue
                break

            if allow_not_found and response is not None and response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()
        finally:
            if response is not None:
                response.close()

    def _get_paginated_items(self, endpoint, parse_item=None):
        items = []
        start_index = 0

        for _ in range(MAX_LIST_PAGES):
            payload = self._request(
                endpoint,
                params={
                    "items_per_page": ITEMS_PER_PAGE,
                    "start_index": start_index,
                },
                allow_not_found=True,
            )
            if payload is None:
                return items

            page_items = payload.get("items") or []
            total = payload.get("total_results")
            page_count = len(page_items)

            if parse_item is None:
                items.extend(page_items)
            else:
                items.extend(parse_item(item) for item in page_items)

            # Drop the raw page before the next request so only slim items accumulate.
            del page_items, payload

            start_index += page_count
            if not page_count:
                break
            if total is not None and start_index >= total:
                break
            if page_count < ITEMS_PER_PAGE:
                break

        return items

    def get_company_profile(self, company_number):
        return self._request(f"/company/{company_number}")

    def get_company_charges(self, company_number, parse_item=None):
        return self._get_paginated_items(
            f"/company/{company_number}/charges",
            parse_item=parse_item,
        )

    def get_company_pscs(self, company_number, parse_item=None):
        return self._get_paginated_items(
            f"/company/{company_number}/persons-with-significant-control",
            parse_item=parse_item,
        )

    def get_company_officers(self, company_number, parse_item=None):
        return self._get_paginated_items(
            f"/company/{company_number}/officers",
            parse_item=parse_item,
        )
