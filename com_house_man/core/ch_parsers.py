from datetime import datetime


def parse_api_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def extract_psc_id(item):
    self_link = (item.get("links") or {}).get("self", "")
    marker = "/persons-with-significant-control/"
    if marker in self_link:
        return self_link.split(marker, 1)[1].strip("/")
    etag = item.get("etag", "")
    if etag:
        return etag.strip('"')
    name = item.get("name", "unknown")
    notified_on = item.get("notified_on", "")
    return f"{name}-{notified_on}"


def extract_charge_code(item, company_number):
    code = (item.get("charge_code") or "").strip()
    if code:
        return code
    charge_number = item.get("charge_number")
    if charge_number is not None:
        return f"{company_number}-{charge_number}"
    created_on = item.get("created_on", "unknown")
    return f"{company_number}-{created_on}"


def parse_company_profile(profile):
    accounts = profile.get("accounts") or {}
    next_accounts = accounts.get("next_accounts") or {}
    accounting_reference_date = accounts.get("accounting_reference_date") or {}
    last_accounts = accounts.get("last_accounts") or {}
    confirmation = profile.get("confirmation_statement") or {}
    address = profile.get("registered_office_address") or {}

    return {
        "company_name": profile.get("company_name", "") or "",
        "company_status": profile.get("company_status", "") or "",
        "company_type": profile.get("type", "") or "",
        "jurisdiction": profile.get("jurisdiction", "") or "",
        "date_of_creation": parse_api_date(profile.get("date_of_creation")),
        "sic_codes": profile.get("sic_codes") or [],
        "registered_premises": address.get("premises", "") or "",
        "registered_address_line_1": address.get("address_line_1", "") or "",
        "registered_address_line_2": address.get("address_line_2", "") or "",
        "registered_locality": address.get("locality", "") or "",
        "registered_region": address.get("region", "") or "",
        "registered_postal_code": address.get("postal_code", "") or "",
        "registered_country": address.get("country", "") or "",
        "registered_po_box": address.get("po_box", "") or "",
        "registered_care_of": address.get("care_of", "") or "",
        "accounts_next_due": parse_api_date(
            next_accounts.get("due_on") or accounts.get("next_due")
        ),
        "accounts_overdue": bool(
            next_accounts.get("overdue") if "overdue" in next_accounts else accounts.get("overdue")
        ),
        "confirmation_next_due": parse_api_date(confirmation.get("next_due")),
        "confirmation_overdue": bool(confirmation.get("overdue")),
        "has_insolvency_history": bool(profile.get("has_insolvency_history")),
        "accounts_ref_day": accounting_reference_date.get("day"),
        "accounts_ref_month": accounting_reference_date.get("month"),
        "accounts_last_made_up": parse_api_date(last_accounts.get("made_up_to")),
        "accounts_category": last_accounts.get("type", "") or "",
    }


def parse_charge_item(item, company_number):
    particulars = item.get("particulars") or {}
    persons_entitled = [
        (entry.get("name") or "").strip()
        for entry in (item.get("persons_entitled") or [])
        if (entry.get("name") or "").strip()
    ]

    return {
        "charge_code": extract_charge_code(item, company_number),
        "charge_number": item.get("charge_number"),
        "status": item.get("status", "") or "",
        "persons_entitled_names": persons_entitled,
        "contains_fixed_charge": bool(particulars.get("contains_fixed_charge")),
        "contains_floating_charge": bool(particulars.get("contains_floating_charge")),
        "floating_charge_covers_all": bool(particulars.get("floating_charge_covers_all")),
        "contains_negative_pledge": bool(particulars.get("contains_negative_pledge")),
        "created_on": parse_api_date(item.get("created_on")),
        "delivered_on": parse_api_date(item.get("delivered_on")),
        "satisfied_on": parse_api_date(item.get("satisfied_on")),
    }


def parse_psc_item(item):
    ceased_on = parse_api_date(item.get("ceased_on"))
    identification = item.get("identification") or {}
    registration_number = (identification.get("registration_number") or "").strip()
    return {
        "psc_id": extract_psc_id(item),
        "kind": item.get("kind", "") or "",
        "name": item.get("name", "") or "",
        "ceased": bool(ceased_on or item.get("ceased")),
        "notified_on": parse_api_date(item.get("notified_on")),
        "ceased_on": ceased_on,
        "natures_of_control": item.get("natures_of_control") or [],
        "controller_company_number": normalize_company_number(registration_number),
    }


def normalize_company_number(value):
    value = (value or "").strip().upper()
    if not value:
        return ""
    if value.isdigit():
        return value.zfill(8)
    return value
