import time

import requests
from django.conf import settings


BASE_URL = "https://api.company-information.service.gov.uk"
MIN_REQUEST_INTERVAL = 0.55
RATE_LIMIT_BACKOFF_SECONDS = 60


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

    def _request(self, endpoint, params=None):
        self._throttle()
        url = f"{BASE_URL}{endpoint}"
        response = requests.get(
            url,
            auth=self.auth,
            params=params,
            timeout=self.timeout,
        )
        CompaniesHouseClient._last_request_at = time.monotonic()

        if response.status_code == 429:
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
            self._throttle()
            response = requests.get(
                url,
                auth=self.auth,
                params=params,
                timeout=self.timeout,
            )
            CompaniesHouseClient._last_request_at = time.monotonic()

        response.raise_for_status()
        return response.json()

    def get_company_profile(self, company_number):
        return self._request(f"/company/{company_number}")

    def get_company_charges(self, company_number):
        return self._request(f"/company/{company_number}/charges").get("items", [])

    def get_company_pscs(self, company_number):
        endpoint = f"/company/{company_number}/persons-with-significant-control"
        return self._request(endpoint).get("items", [])
