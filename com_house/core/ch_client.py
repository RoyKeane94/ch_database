import time

import requests
from django.conf import settings


BASE_URL = "https://api.company-information.service.gov.uk"


class CompaniesHouseClient:
    def __init__(self):
        self.auth = (settings.COMPANIES_HOUSE_API_KEY, "")
        self.timeout = 30

    def _request(self, endpoint, params=None):
        url = f"{BASE_URL}{endpoint}"
        response = requests.get(
            url,
            auth=self.auth,
            params=params,
            timeout=self.timeout,
        )

        if response.status_code == 429:
            time.sleep(60)
            response = requests.get(
                url,
                auth=self.auth,
                params=params,
                timeout=self.timeout,
            )

        response.raise_for_status()
        return response.json()

    def get_company_profile(self, company_number):
        return self._request(f"/company/{company_number}")

    def get_company_charges(self, company_number):
        return self._request(f"/company/{company_number}/charges").get("items", [])

    def get_company_pscs(self, company_number):
        endpoint = f"/company/{company_number}/persons-with-significant-control"
        return self._request(endpoint).get("items", [])
