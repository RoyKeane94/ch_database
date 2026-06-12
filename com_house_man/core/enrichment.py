from django.db import transaction
from django.utils import timezone
from requests import HTTPError

from core.ch_parsers import parse_charge_item, parse_company_profile, parse_psc_item
from core.models import Charge, Company, PSC, PersonEntitled


def format_enrichment_error(exc):
    if isinstance(exc, HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
    return str(exc)[:400]


def get_or_create_persons_entitled(names):
    persons = []
    for name in names:
        person, _ = PersonEntitled.objects.get_or_create(name=name)
        persons.append(person)
    return persons


@transaction.atomic
def save_company_enrichment(company, profile, charge_items, psc_items, fetched_at=None):
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
                ceased=parsed["ceased"],
                notified_on=parsed["notified_on"],
                ceased_on=parsed["ceased_on"],
                natures_of_control=parsed["natures_of_control"],
            )
        )
    if psc_models:
        PSC.objects.bulk_create(psc_models)


def enrich_company(client, company):
    profile = client.get_company_profile(company.company_number)
    charges = client.get_company_charges(company.company_number)
    pscs = client.get_company_pscs(company.company_number)
    save_company_enrichment(company, profile, charges, pscs)
