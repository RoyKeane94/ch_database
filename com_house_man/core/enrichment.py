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
from core.models import Charge, Officer, PSC, PersonEntitled


TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
BULK_CREATE_BATCH = 250


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


def _clean_person_name(name):
    return " ".join((name or "").split())


def get_or_create_persons_entitled(names):
    cleaned = []
    seen = set()
    for name in names:
        value = _clean_person_name(name)
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        return []

    existing = {
        person.name: person
        for person in PersonEntitled.objects.filter(name__in=cleaned)
    }
    missing = [PersonEntitled(name=name) for name in cleaned if name not in existing]
    if missing:
        PersonEntitled.objects.bulk_create(
            missing, ignore_conflicts=True, batch_size=BULK_CREATE_BATCH
        )
        existing = {
            person.name: person
            for person in PersonEntitled.objects.filter(name__in=cleaned)
        }
    return [existing[name] for name in cleaned if name in existing]


def _parsed_charge(item, company_number, already_parsed):
    if already_parsed:
        return item
    return parse_charge_item(item, company_number)


def _parsed_psc(item, already_parsed):
    if already_parsed:
        return item
    return parse_psc_item(item)


def _parsed_officer(item, company_number, already_parsed):
    if already_parsed:
        return item
    return parse_officer_item(item, company_number)


def _save_charges(company, charge_items, fetched_at, already_parsed):
    charge_models = []
    holders_by_code = []
    seen_codes = set()

    for item in charge_items:
        parsed = _parsed_charge(item, company.company_number, already_parsed)
        charge_code = parsed["charge_code"]
        if charge_code in seen_codes:
            continue
        seen_codes.add(charge_code)
        charge_models.append(
            Charge(
                charge_code=charge_code,
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
        )
        holders_by_code.append((charge_code, parsed.get("persons_entitled_names") or []))

    if not charge_models:
        return

    Charge.objects.bulk_create(charge_models, batch_size=BULK_CREATE_BATCH)

    all_names = [
        name
        for _code, names in holders_by_code
        for name in names
    ]
    person_map = {
        person.name: person for person in get_or_create_persons_entitled(all_names)
    }
    through = Charge.persons_entitled.through
    links = []
    seen_links = set()
    for charge_code, names in holders_by_code:
        for name in names:
            person = person_map.get(_clean_person_name(name))
            if person is None:
                continue
            link_key = (charge_code, person.pk)
            if link_key in seen_links:
                continue
            seen_links.add(link_key)
            links.append(
                through(charge_id=charge_code, personentitled_id=person.pk)
            )
    if links:
        through.objects.bulk_create(
            links, ignore_conflicts=True, batch_size=BULK_CREATE_BATCH
        )


def _save_pscs(company, psc_items, already_parsed):
    psc_models = []
    seen_ids = set()
    for item in psc_items:
        parsed = _parsed_psc(item, already_parsed)
        psc_id = parsed["psc_id"]
        if psc_id in seen_ids:
            continue
        seen_ids.add(psc_id)
        psc_models.append(
            PSC(
                psc_id=psc_id,
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
        PSC.objects.bulk_create(psc_models, batch_size=BULK_CREATE_BATCH)


def _save_officers(company, officer_items, already_parsed):
    officer_models = []
    seen_ids = set()
    for item in officer_items:
        parsed = _parsed_officer(item, company.company_number, already_parsed)
        officer_id = parsed["officer_id"]
        if officer_id in seen_ids:
            continue
        seen_ids.add(officer_id)
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
        Officer.objects.bulk_create(officer_models, batch_size=BULK_CREATE_BATCH)


@transaction.atomic
def save_company_enrichment(
    company,
    profile,
    charge_items,
    psc_items,
    officer_items=None,
    fetched_at=None,
    *,
    already_parsed=False,
):
    fetched_at = fetched_at or timezone.now()
    profile_data = profile if already_parsed else parse_company_profile(profile)

    for field, value in profile_data.items():
        setattr(company, field, value)

    company.enrichment_error = ""
    company.needs_enrichment = False
    company.last_fetched_at = fetched_at
    company.save()

    Charge.objects.filter(company=company).delete()
    PSC.objects.filter(company=company).delete()
    Officer.objects.filter(company=company).delete()

    _save_charges(company, charge_items, fetched_at, already_parsed)
    _save_pscs(company, psc_items, already_parsed)
    _save_officers(company, officer_items or [], already_parsed)


def enrich_company(client, company):
    number = company.company_number
    # Parse each payload before the next request so only slim dicts overlap.
    profile = parse_company_profile(client.get_company_profile(number))
    charges = client.get_company_charges(
        number, parse_item=lambda item: parse_charge_item(item, number)
    )
    pscs = client.get_company_pscs(number, parse_item=parse_psc_item)
    officers = client.get_company_officers(
        number, parse_item=lambda item: parse_officer_item(item, number)
    )
    save_company_enrichment(
        company, profile, charges, pscs, officers, already_parsed=True
    )
