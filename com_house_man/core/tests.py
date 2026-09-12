from datetime import date
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from requests import HTTPError

from core.ch_client import ITEMS_PER_PAGE, CompaniesHouseClient
from core.ch_parsers import extract_officer_id, parse_officer_item
from core.enrichment import is_transient_enrichment_error, save_company_enrichment
from core.models import Company, Officer
from core.signals import (
    build_opportunity_strip,
    group_holders_by_normalized,
    normalize_holder_name,
    officer_age,
)
from core.teletext import format_officer_role


class OfficerParserTests(SimpleTestCase):
    def test_extract_officer_id_from_appointment_link(self):
        item = {"links": {"self": "/company/01234567/appointments/abc-123"}}
        self.assertEqual(extract_officer_id(item, "01234567"), "01234567-abc-123")

    def test_parse_officer_item(self):
        parsed = parse_officer_item(
            {
                "name": "SMITH, Jane",
                "officer_role": "director",
                "appointed_on": "2020-01-15",
                "resigned_on": None,
                "nationality": "British",
                "occupation": "Accountant",
                "country_of_residence": "England",
                "date_of_birth": {"month": 3, "year": 1978},
                "person_number": "123456789001",
                "links": {"self": "/company/01234567/appointments/abc-123"},
            },
            "01234567",
        )
        self.assertEqual(parsed["officer_id"], "01234567-abc-123")
        self.assertEqual(parsed["name"], "SMITH, Jane")
        self.assertEqual(parsed["officer_role"], "director")
        self.assertEqual(parsed["appointed_on"], date(2020, 1, 15))
        self.assertIsNone(parsed["resigned_on"])
        self.assertEqual(parsed["date_of_birth_month"], 3)
        self.assertEqual(parsed["date_of_birth_year"], 1978)

    def test_format_officer_role(self):
        self.assertEqual(format_officer_role("llp-designated-member"), "LLP designated member")
        self.assertEqual(format_officer_role("director"), "Director")
        self.assertEqual(format_officer_role(""), "—")


class CompaniesHouseClientTests(SimpleTestCase):
    def _response(self, status_code, payload=None):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = payload or {}
        if status_code >= 400:
            response.raise_for_status.side_effect = HTTPError(response=response)
        else:
            response.raise_for_status.return_value = None
        return response

    @patch("core.ch_client.requests.get")
    def test_list_404_returns_empty(self, mock_get):
        mock_get.return_value = self._response(404)
        client = CompaniesHouseClient(min_interval=0)
        self.assertEqual(client.get_company_charges("01234567"), [])
        self.assertEqual(client.get_company_pscs("01234567"), [])
        self.assertEqual(client.get_company_officers("01234567"), [])

    @patch("core.ch_client.requests.get")
    def test_list_paginates_until_complete(self, mock_get):
        first_page = [{"name": "One"}] * ITEMS_PER_PAGE
        second_page = [{"name": "Two"}]
        mock_get.side_effect = [
            self._response(
                200,
                {
                    "items": first_page,
                    "total_results": ITEMS_PER_PAGE + 1,
                    "start_index": 0,
                },
            ),
            self._response(
                200,
                {
                    "items": second_page,
                    "total_results": ITEMS_PER_PAGE + 1,
                    "start_index": ITEMS_PER_PAGE,
                },
            ),
        ]
        client = CompaniesHouseClient(min_interval=0)
        items = client.get_company_officers("01234567")
        self.assertEqual(len(items), ITEMS_PER_PAGE + 1)
        self.assertEqual(mock_get.call_count, 2)


class EnrichmentOfficerTests(TestCase):
    def test_save_company_enrichment_stores_officers(self):
        company = Company.objects.create(company_number="01234567", company_name="Test Ltd")
        save_company_enrichment(
            company,
            {"company_name": "Test Ltd", "company_status": "active"},
            [],
            [],
            [
                {
                    "name": "SMITH, Jane",
                    "officer_role": "director",
                    "appointed_on": "2020-01-15",
                    "links": {"self": "/company/01234567/appointments/abc-123"},
                }
            ],
        )
        officer = Officer.objects.get(officer_id="01234567-abc-123")
        self.assertEqual(officer.name, "SMITH, Jane")
        self.assertEqual(officer.officer_role, "director")
        self.assertEqual(officer.appointed_on, date(2020, 1, 15))

    def test_rate_limit_is_transient(self):
        response = Mock()
        response.status_code = 429
        self.assertTrue(is_transient_enrichment_error(HTTPError(response=response)))
        self.assertFalse(is_transient_enrichment_error(HTTPError(response=Mock(status_code=404))))


class SignalTests(SimpleTestCase):
    def test_normalize_holder_name_merges_barclays_variants(self):
        a = normalize_holder_name("Barclays Bank PLC")
        b = normalize_holder_name("BARCLAYS BANK PLC")
        self.assertEqual(a, b)

    def test_officer_age(self):
        officer = Officer(date_of_birth_year=1980, date_of_birth_month=6)
        self.assertEqual(officer_age(officer, date(2020, 7, 1)), 40)

    def test_group_holders_by_normalized(self):
        class Holder:
            def __init__(self, id, name, charge_count=1, company_count=2):
                self.id = id
                self.name = name
                self.charge_count = charge_count
                self.company_count = company_count
                self.active_company_count = 1

        grouped = group_holders_by_normalized(
            [
                Holder(1, "Barclays Bank PLC", 10, 5),
                Holder(2, "BARCLAYS BANK PLC", 3, 2),
            ]
        )
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["charge_count"], 13)
        self.assertEqual(len(grouped[0]["holder_ids"]), 2)


class OpportunityStripTests(TestCase):
    def test_build_opportunity_strip_flags_overdue_accounts(self):
        company = Company.objects.create(
            company_number="99999999",
            company_name="Overdue Ltd",
            accounts_overdue=True,
        )
        chips = build_opportunity_strip(company, [], [], [], {"has_links": False})
        texts = [chip["text"] for chip in chips]
        self.assertTrue(any("Accounts overdue" in text for text in texts))
