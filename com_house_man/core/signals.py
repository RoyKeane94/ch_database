"""Opportunity signals for company search and detail views."""

import re
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, DateField, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.core.cache import cache
from django.utils import timezone

from core.company_tree import CORPORATE_PSC_KIND
from core.models import Charge, Officer, PSC


def active_charge_q(prefix=""):
    if prefix and not prefix.endswith("__"):
        prefix = f"{prefix}__"
    return (
        Q(**{f"{prefix}satisfied_on__isnull": True})
        & ~Q(**{f"{prefix}status__icontains": "fully-satisfied"})
        & ~Q(**{f"{prefix}status__icontains": "fully satisfied"})
    )

INDIVIDUAL_PSC_KIND = "individual-person-with-significant-control"
PSC_LOOKBACK_MONTHS = 24
PSC_RECENT_MONTHS = 12

HOLDER_SUFFIXES = (
    "plc",
    "limited",
    "ltd",
    "llp",
    "inc",
    "uk",
    "the",
    "co",
    "company",
    "holdings",
    "group",
    "international",
    "finance",
    "financial",
    "services",
)


def normalize_holder_name(name):
    """Collapse near-duplicate charge holder names for grouping."""
    if not name:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for suffix in HOLDER_SUFFIXES:
        cleaned = re.sub(rf"\b{re.escape(suffix)}\b", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or name.lower().strip()


def officer_age(officer, ref_date=None):
    ref_date = ref_date or timezone.localdate()
    if not officer.date_of_birth_year:
        return None
    month = officer.date_of_birth_month or 1
    try:
        dob = date(officer.date_of_birth_year, month, 1)
    except ValueError:
        dob = date(officer.date_of_birth_year, 1, 1)
    age = ref_date.year - dob.year
    if (ref_date.month, ref_date.day) < (dob.month, 1):
        age -= 1
    return age


def active_officers(officers):
    return [officer for officer in officers if not officer.resigned_on]


def officer_age_stats(officers, ref_date=None):
    ages = [
        age
        for officer in active_officers(officers)
        if (age := officer_age(officer, ref_date)) is not None
    ]
    if not ages:
        return None, None
    return min(ages), round(sum(ages) / len(ages))


def psc_cutoff(months=PSC_LOOKBACK_MONTHS):
    return timezone.localdate() - timedelta(days=months * 30)


def is_outstanding_charge(charge):
    if charge.satisfied_on:
        return False
    status = (charge.status or "").lower()
    return "fully-satisfied" not in status and "fully satisfied" not in status


def charge_summary(charges):
    outstanding = [charge for charge in charges if is_outstanding_charge(charge)]
    if not outstanding:
        return {
            "count": 0,
            "latest_created": None,
            "top_holder": "",
            "top_holder_id": None,
        }

    latest_created = max(
        (charge.created_on for charge in outstanding if charge.created_on),
        default=None,
    )
    holder_counts = {}
    holder_names = {}
    for charge in outstanding:
        for person in charge.persons_entitled.all():
            holder_counts[person.id] = holder_counts.get(person.id, 0) + 1
            holder_names[person.id] = person.name
    top_holder_id = None
    top_count = 0
    top_holder = ""
    for holder_id, count in holder_counts.items():
        if count > top_count:
            top_count = count
            top_holder_id = holder_id
            top_holder = holder_names[holder_id]
    return {
        "count": len(outstanding),
        "latest_created": latest_created,
        "top_holder": top_holder,
        "top_holder_id": top_holder_id,
    }


def psc_change_summary(pscs, months=PSC_LOOKBACK_MONTHS):
    cutoff = psc_cutoff(months)
    recent_cutoff = psc_cutoff(PSC_RECENT_MONTHS)
    latest = None
    recent_count = 0
    new_corporate = False
    for psc in pscs:
        for event_date in (psc.notified_on, psc.ceased_on):
            if event_date and event_date >= cutoff:
                recent_count += 1
                if latest is None or event_date > latest:
                    latest = event_date
        if (
            not psc.ceased
            and psc.kind == CORPORATE_PSC_KIND
            and psc.notified_on
            and psc.notified_on >= recent_cutoff
        ):
            new_corporate = True
    return {
        "latest_change": latest,
        "recent_count": recent_count,
        "new_corporate": new_corporate,
    }


def detect_psc_flip(pscs, months=PSC_LOOKBACK_MONTHS):
    cutoff = psc_cutoff(months)
    ceased_individuals = [
        psc
        for psc in pscs
        if psc.kind == INDIVIDUAL_PSC_KIND
        and psc.ceased
        and psc.ceased_on
        and psc.ceased_on >= cutoff
    ]
    new_corporates = [
        psc
        for psc in pscs
        if psc.kind == CORPORATE_PSC_KIND
        and not psc.ceased
        and psc.notified_on
        and psc.notified_on >= cutoff
    ]
    return bool(ceased_individuals and new_corporates)


def detect_new_subsidiary(ownership_tree, months=PSC_LOOKBACK_MONTHS):
    if not ownership_tree.get("has_links"):
        return False
    cutoff = psc_cutoff(months)
    for item in ownership_tree.get("sequence", []):
        if item.get("kind") != "node":
            continue
        node = item.get("node") or {}
        if node.get("role") != "subsidiary":
            continue
        return True
    return False


def acquisition_signals(company, charges, pscs, officers, ownership_tree):
    psc_info = psc_change_summary(pscs)
    signals = []
    if psc_info["new_corporate"]:
        signals.append("New corporate PSC")
    if detect_psc_flip(pscs):
        signals.append("Individual → corporate")
    if ownership_tree.get("has_links") and any(
        item.get("kind") == "node"
        and (item.get("node") or {}).get("role") == "subsidiary"
        for item in ownership_tree.get("sequence", [])
    ):
        signals.append("Subsidiary in tree")
    if company.date_of_creation and company.date_of_creation >= psc_cutoff(PSC_RECENT_MONTHS):
        signals.append("Recently incorporated")
    charge_info = charge_summary(charges)
    if charge_info["count"] >= 3:
        signals.append("Heavy charge stack")
    return signals


def build_opportunity_strip(company, charges, pscs, officers, ownership_tree):
    chips = []
    charge_info = charge_summary(charges)
    if charge_info["count"]:
        latest = charge_info["latest_created"]
        latest_label = latest.strftime("%b %Y") if latest else "—"
        holder = charge_info["top_holder"] or "unknown holder"
        chips.append(
            {
                "text": f"{charge_info['count']} outstanding charge"
                f"{'s' if charge_info['count'] != 1 else ''}"
                f" · latest {latest_label} · {holder}",
                "tone": "warn",
            }
        )
    else:
        chips.append({"text": "No outstanding charges", "tone": "muted"})

    psc_info = psc_change_summary(pscs)
    if psc_info["latest_change"]:
        chips.append(
            {
                "text": f"PSC change {psc_info['latest_change'].strftime('%b %Y')}",
                "tone": "accent",
            }
        )
    elif not pscs:
        chips.append({"text": "No PSCs synced", "tone": "muted"})
    else:
        chips.append({"text": "No PSC change (24m)", "tone": "muted"})

    active = active_officers(officers)
    if not officers:
        chips.append({"text": "No officers synced", "tone": "muted"})
    elif not active:
        chips.append({"text": "No active officers", "tone": "warn"})
    else:
        youngest, avg_age = officer_age_stats(officers)
        if youngest is not None:
            chips.append(
                {
                    "text": f"Directors youngest {youngest}"
                    + (f" · avg {avg_age}" if avg_age is not None else ""),
                    "tone": "default",
                }
            )

    acq = acquisition_signals(company, charges, pscs, officers, ownership_tree)
    if acq:
        chips.append({"text": " · ".join(acq[:2]), "tone": "signal"})

    if company.accounts_overdue:
        chips.append({"text": "Accounts overdue", "tone": "danger"})
    if company.confirmation_overdue:
        chips.append({"text": "Confirmation overdue", "tone": "danger"})
    if company.needs_enrichment and not company.last_fetched_at:
        chips.append({"text": "Pending API fetch", "tone": "muted"})

    return chips


def annotate_company_row(company, *, charges=None, pscs=None, officers=None):
    """Attach display-friendly signal fields to a company for list rows."""
    if not company.last_fetched_at:
        company.signal_charges_count = 0
        company.signal_charges_latest = None
        company.signal_charges_holder = ""
        company.signal_charges_holder_id = None
        company.signal_psc_change = None
        company.signal_youngest_director = None
        company.signal_avg_director_age = None
        company.signal_acquisition = []
        company.signal_location = _location_label(company)
        company.signal_sic_primary = (company.sic_codes or [None])[0]
        return company

    if charges is None:
        charges = list(company.charges.prefetch_related("persons_entitled").all())
    if pscs is None:
        pscs = list(company.pscs.all())
    if officers is None:
        officers = list(
            company.officers.filter(resigned_on__isnull=True).only(
                "date_of_birth_month",
                "date_of_birth_year",
                "resigned_on",
            )
        )

    charge_info = charge_summary(charges)
    psc_info = psc_change_summary(pscs)
    youngest, avg_age = officer_age_stats(officers)
    acq = acquisition_signals(company, charges, pscs, officers, {"has_links": False})

    company.signal_charges_count = charge_info["count"]
    company.signal_charges_latest = charge_info["latest_created"]
    company.signal_charges_holder = charge_info["top_holder"]
    company.signal_charges_holder_id = charge_info["top_holder_id"]
    company.signal_psc_change = psc_info["latest_change"]
    company.signal_youngest_director = youngest
    company.signal_avg_director_age = avg_age
    company.signal_acquisition = acq
    company.signal_location = _location_label(company)
    company.signal_sic_primary = (company.sic_codes or [None])[0]
    return company


def _location_label(company):
    parts = []
    if company.registered_postal_code:
        parts.append(company.registered_postal_code)
    if company.registered_region:
        parts.append(company.registered_region)
    elif company.registered_locality:
        parts.append(company.registered_locality)
    return ", ".join(parts) or "—"


def db_annotate_list_signals(queryset):
    """Subquery annotations for charge/PSC sort — avoids charge/psc JOINs on every row."""
    outstanding_count = (
        Charge.objects.filter(company_id=OuterRef("pk"))
        .filter(active_charge_q())
        .order_by()
        .values("company")
        .annotate(c=Count("pk"))
        .values("c")[:1]
    )
    latest_charge = (
        Charge.objects.filter(company_id=OuterRef("pk"))
        .filter(active_charge_q())
        .order_by("-created_on")
        .values("created_on")[:1]
    )
    psc_change = (
        PSC.objects.filter(
            company_id=OuterRef("pk"),
            notified_on__gte=psc_cutoff(),
        )
        .order_by("-notified_on")
        .values("notified_on")[:1]
    )
    return queryset.annotate(
        outstanding_charge_count=Coalesce(
            Subquery(outstanding_count, output_field=IntegerField()),
            0,
        ),
        latest_outstanding_charge=Subquery(latest_charge, output_field=DateField()),
        psc_latest_change=Subquery(psc_change, output_field=DateField()),
    )


def enrich_company_list_page(companies):
    """Batch-load charges, PSCs, and officers for one results page."""
    if not companies:
        return companies

    enriched = [company for company in companies if company.last_fetched_at]
    if not enriched:
        for company in companies:
            annotate_company_row(company)
        return companies

    company_ids = [company.company_number for company in enriched]
    charges_map = defaultdict(list)
    for charge in Charge.objects.filter(company_id__in=company_ids).prefetch_related(
        "persons_entitled"
    ):
        charges_map[charge.company_id].append(charge)

    pscs_map = defaultdict(list)
    for psc in PSC.objects.filter(company_id__in=company_ids).only(
        "company_id",
        "kind",
        "ceased",
        "notified_on",
        "ceased_on",
    ):
        pscs_map[psc.company_id].append(psc)

    officers_map = defaultdict(list)
    for officer in Officer.objects.filter(
        company_id__in=company_ids,
        resigned_on__isnull=True,
    ).only("company_id", "date_of_birth_month", "date_of_birth_year", "resigned_on"):
        officers_map[officer.company_id].append(officer)

    for company in companies:
        if not company.last_fetched_at:
            annotate_company_row(company)
            continue
        annotate_company_row(
            company,
            charges=charges_map[company.company_number],
            pscs=pscs_map[company.company_number],
            officers=officers_map[company.company_number],
        )
    return companies


def holder_sic_peers(holder_ids, sic_codes, exclude_number, limit=8):
    """Companies backed by the same holder(s) in overlapping SIC codes."""
    if not holder_ids or not sic_codes:
        return []

    from core.models import Company
    from core.sic_lookup import company_sic_filter_q

    qs = (
        Company.objects.filter(company_sic_filter_q(sic_codes))
        .exclude(company_number=exclude_number)
        .filter(
            charges__persons_entitled__id__in=holder_ids,
        )
        .distinct()
        .only("company_number", "company_name", "company_status")[:limit]
    )
    return list(qs)


def charges_this_month_count():
    cache_key = "charges_this_month_v1"
    cache_seconds = 300
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        cached = None

    today = timezone.localdate()
    first_of_month = today.replace(day=1)
    count = Charge.objects.filter(created_on__gte=first_of_month).count()
    try:
        cache.set(cache_key, count, cache_seconds)
    except Exception:
        pass
    return count


def group_holders_by_normalized(holders):
    """Merge holder rows that normalize to the same key."""
    groups = {}
    for holder in holders:
        key = normalize_holder_name(holder.name)
        if key not in groups:
            groups[key] = {
                "key": key,
                "display_name": holder.name,
                "holder_ids": [],
                "charge_count": 0,
                "company_count": 0,
                "active_company_count": 0,
                "new_charges_month": 0,
                "variants": [],
            }
        group = groups[key]
        group["holder_ids"].append(holder.id)
        group["variants"].append(holder.name)
        group["charge_count"] += getattr(holder, "charge_count", 0) or 0
        group["company_count"] += getattr(holder, "company_count", 0) or 0
        group["active_company_count"] += getattr(holder, "active_company_count", 0) or 0
        if len(holder.name) < len(group["display_name"]):
            group["display_name"] = holder.name
    return sorted(groups.values(), key=lambda item: (-item["company_count"], item["display_name"]))
