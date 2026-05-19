import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from requests import HTTPError

from core.ch_client import CompaniesHouseClient
from core.models import Charge, Company, PSCEvent

SLEEP_SECONDS = 2.5
BATCH_SIZE = 200


class Command(BaseCommand):
    help = "Enrich pending companies with Companies House charges and PSC data."

    def handle(self, *args, **options):
        if not Company.objects.filter(needs_enrichment=True).exists():
            self.stdout.write("No companies queued for enrichment.")
            return

        client = CompaniesHouseClient()
        companies = Company.objects.filter(needs_enrichment=True)[:BATCH_SIZE]
        success_count = 0
        failure_count = 0

        for company in companies:
            try:
                profile = client.get_company_profile(company.company_number)
                charges = client.get_company_charges(company.company_number)
                psc_items = client.get_company_pscs(company.company_number)
                self._save_company_enrichment(company, profile, charges, psc_items)
                success_count += 1
                self.stdout.write(f"Enriched {company.company_number}")
            except Exception as exc:  # noqa: BLE001
                failure_count += 1
                company.enrichment_error = self._format_error(exc)
                company.needs_enrichment = False
                company.last_enriched_at = None
                company.save(
                    update_fields=["enrichment_error", "needs_enrichment", "last_enriched_at"]
                )
                self.stderr.write(
                    f"Failed {company.company_number}: {company.enrichment_error}"
                )

            time.sleep(SLEEP_SECONDS)

        self.stdout.write(
            self.style.SUCCESS(
                f"Enrichment run complete: succeeded={success_count}, failed={failure_count}"
            )
        )

    def _save_company_enrichment(self, company, profile, charges, psc_items):
        with transaction.atomic():
            self._update_blank_profile_fields(company, profile)
            company.enrichment_error = ""
            company.needs_enrichment = False
            company.last_enriched_at = timezone.now()
            company.save()

            company.charges.all().delete()
            company.psc_events.all().delete()

            charge_models = [self._build_charge(company, item) for item in charges]
            psc_models = [self._build_psc(company, item) for item in psc_items]

            if charge_models:
                Charge.objects.bulk_create(charge_models)
            if psc_models:
                PSCEvent.objects.bulk_create(psc_models)

    def _update_blank_profile_fields(self, company, profile):
        accounts = profile.get("accounts") or {}
        accounting_reference_date = accounts.get("accounting_reference_date") or {}
        last_accounts = accounts.get("last_accounts") or {}

        if not company.company_name:
            company.company_name = profile.get("company_name", "") or ""
        if not company.company_status:
            company.company_status = profile.get("company_status", "") or ""
        if not company.incorporated_on:
            company.incorporated_on = self._parse_api_date(profile.get("date_of_creation"))
        if not company.accounts_ref_day:
            company.accounts_ref_day = accounting_reference_date.get("day")
        if not company.accounts_ref_month:
            company.accounts_ref_month = accounting_reference_date.get("month")
        if not company.accounts_last_made_up:
            company.accounts_last_made_up = self._parse_api_date(last_accounts.get("made_up_to"))
        if not company.accounts_category:
            company.accounts_category = last_accounts.get("type", "") or ""
        if not company.sic_codes:
            company.sic_codes = profile.get("sic_codes") or []

    def _build_charge(self, company, item):
        persons_entitled = item.get("persons_entitled") or []
        return Charge(
            company=company,
            charge_code=item.get("charge_code", "") or "",
            holder_name=(persons_entitled[0].get("name", "") if persons_entitled else ""),
            created_on=self._parse_api_date(item.get("created_on")),
            satisfied_on=self._parse_api_date(item.get("satisfied_on")),
            charge_type=item.get("classification", {}).get("description", "") or "",
            status=item.get("status", "") or "",
        )

    def _build_psc(self, company, item):
        return PSCEvent(
            company=company,
            psc_name=item.get("name", "") or "",
            psc_kind=item.get("kind", "") or "",
            notified_on=self._parse_api_date(item.get("notified_on")),
            ceased_on=self._parse_api_date(item.get("ceased_on")),
            nature_of_control=item.get("natures_of_control") or [],
        )

    def _format_error(self, exc):
        if isinstance(exc, HTTPError) and exc.response is not None:
            return f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
        return str(exc)[:400]

    def _parse_api_date(self, value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
