from django.db import transaction
from django.utils import timezone
from requests import ConnectionError as RequestsConnectionError
from requests import HTTPError, Timeout

from core.ch_parsers import (
    parse_charge_item,
    parse_company_profile,
    parse_officer_item,
    parse_psc_item,
)
from core.models import Charge, Company, Officer, PSC, PersonEntitled


TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


def format_enrichment_error(exc):
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
    return str(exc)[:400]


def is_transient_enrichment_error(exc):
    if isinstance(exc, (Timeout, RequestsConnectionError)):
        return True
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code in TRANSIENT_HTTP_STATUSES
    return False


def get_or_create_persons_entitled(names):
    persons = []
    for name in names:
        cleaned = " ".join((name or "").split())
        if not cleaned:
            continue
        person, _ = PersonEntitled.objects.get_or_create(name=cleaned)
        persons.append(person)
    return persons


@transaction.atomic
def save_company_enrichment(
    company, profile, charge_items, psc_items, officer_items=None, fetched_at=None
):
    fetched_at = fetched_at or timezone.now()
    profile_data = parse_company_profile(profile)

    for field, value in profile_data.items():
        setattr(company, field, value)

    company.enrichment_error = ""
    company.needs_enrichment = False
    company.last_fetched_at = fetched_at
    company.save()

    company.charges.all().delete()
    company.pscs.all().delete()
    company.officers.all().delete()

    for item in charge_items:
        parsed = parse_charge_item(item, company.company_number)
        charge = Charge.objects.create(
            charge_code=parsed["charge_code"],
            company=company,
            charge_number=parsed["charge_number"],
            status=parsed["status"],
            contains_fixed_charge=parsed["contains_fixed_charge"],
            contains_floating_charge=parsed["contains_floating_charge"],
            floating_charge_covers_all=parsed["floating_charge_covers_all"],
            contains_negative_pledge=parsed["contains_negative_pledge"],
            created_on=parsed["created_on"],
            delivered_on=parsed["delivered_on"],
            satisfied_on=parsed["satisfied_on"],
            last_fetched_at=fetched_at,
        )
        if parsed["persons_entitled_names"]:
            charge.persons_entitled.set(
                get_or_create_persons_entitled(parsed["persons_entitled_names"])
            )

    psc_models = []
    for item in psc_items:
        parsed = parse_psc_item(item)
        psc_models.append(
            PSC(
                psc_id=parsed["psc_id"],
                company=company,
                kind=parsed["kind"],
                name=parsed["name"],
                controller_company_number=parsed["controller_company_number"],
                ceased=parsed["ceased"],
                notified_on=parsed["notified_on"],
                ceased_on=parsed["ceased_on"],
                natures_of_control=parsed["natures_of_control"],
            )
        )
    if psc_models:
        PSC.objects.bulk_create(psc_models)

    officer_models = []
    seen_officer_ids = set()
    for item in officer_items or []:
        parsed = parse_officer_item(item, company.company_number)
        officer_id = parsed["officer_id"]
        if officer_id in seen_officer_ids:
            continue
        seen_officer_ids.add(officer_id)
        officer_models.append(
            Officer(
                officer_id=officer_id,
                company=company,
                name=parsed["name"],
                officer_role=parsed["officer_role"],
                appointed_on=parsed["appointed_on"],
                resigned_on=parsed["resigned_on"],
                nationality=parsed["nationality"],
                occupation=parsed["occupation"],
                country_of_residence=parsed["country_of_residence"],
                date_of_birth_month=parsed["date_of_birth_month"],
                date_of_birth_year=parsed["date_of_birth_year"],
                person_number=parsed["person_number"],
            )
        )
    if officer_models:
        Officer.objects.bulk_create(officer_models)


def enrich_company(client, company):
    profile = client.get_company_profile(company.company_number)
    charges = client.get_company_charges(company.company_number)
    pscs = client.get_company_pscs(company.company_number)
    officers = client.get_company_officers(company.company_number)
    save_company_enrichment(company, profile, charges, pscs, officers)
