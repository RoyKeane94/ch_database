from datetime import datetime

from django.core.cache import cache
from django.db.models import Count, Exists, IntegerField, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.company_tree import CORPORATE_PSC_KIND
from core.models import Charge, Company, Officer, PersonEntitled, PSC
from core.signals import (
    INDIVIDUAL_PSC_KIND,
    active_charge_q,
    db_annotate_list_signals,
    psc_cutoff,
)
from core.sic_lookup import company_sic_filter_q, find_matching_sic_codes

COMPANY_LIST_FIELDS = (
    "company_number",
    "company_name",
    "company_status",
    "company_type",
    "company_category",
    "accounts_category",
    "created_at",
    "date_of_creation",
    "registered_postal_code",
    "registered_region",
    "registered_locality",
    "sic_codes",
    "accounts_overdue",
    "last_fetched_at",
)

COMPANY_EXPORT_FIELDS = COMPANY_LIST_FIELDS + (
    "registered_postal_code",
)

HOLDER_LIST_FIELDS = (
    "id",
    "name",
)

FACET_COUNTS_CACHE_KEY = "company_facet_counts_v1"
FACET_COUNTS_CACHE_SECONDS = 600


def parse_sic_query(request):
    return request.GET.get("sic", "").strip()


def parse_holder_filters(request):
    return [int(value) for value in request.GET.getlist("holder") if value.isdigit()]


def parse_has_charges(request):
    return request.GET.get("has_charges", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def parse_activity_filter(request):
    activity = request.GET.get("activity", "").strip().lower()
    if activity in {"active", "inactive"}:
        return activity
    return ""


def parse_date_param(request, key):
    raw = request.GET.get(key, "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_int_param(request, key):
    raw = request.GET.get(key, "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def parse_bool_param(request, key):
    return request.GET.get(key, "").strip().lower() in {"1", "true", "yes", "on"}


def parse_signal_filters(request):
    return {
        "outstanding_charges": parse_bool_param(request, "outstanding_charges"),
        "charge_since": parse_date_param(request, "charge_since"),
        "holder_contains": request.GET.get("holder_contains", "").strip(),
        "psc_since": parse_date_param(request, "psc_since"),
        "new_corporate_psc": parse_bool_param(request, "new_corporate_psc"),
        "psc_flip": parse_bool_param(request, "psc_flip"),
        "director_age_under": parse_int_param(request, "director_age_under"),
        "all_directors_over": parse_int_param(request, "all_directors_over"),
        "acquisition_signal": parse_bool_param(request, "acquisition_signal"),
        "accounts_overdue": parse_bool_param(request, "accounts_overdue"),
        "postcode": request.GET.get("postcode", "").strip(),
        "region": request.GET.get("region", "").strip(),
    }


def _filter_outstanding_charges(queryset):
    active_charges = Charge.objects.filter(company_id=OuterRef("pk")).filter(active_charge_q())
    return queryset.filter(Exists(active_charges))


def _filter_charge_since(queryset, since_date):
    recent = Charge.objects.filter(
        company_id=OuterRef("pk"),
        created_on__gte=since_date,
    )
    return queryset.filter(Exists(recent))


def _filter_holder_contains(queryset, text):
    linked = Charge.objects.filter(
        company_id=OuterRef("pk"),
        persons_entitled__name__icontains=text,
    )
    return queryset.filter(Exists(linked))


def _filter_psc_since(queryset, since_date):
    changed = PSC.objects.filter(company_id=OuterRef("pk")).filter(
        Q(notified_on__gte=since_date) | Q(ceased_on__gte=since_date)
    )
    return queryset.filter(Exists(changed))


def _filter_new_corporate_psc(queryset):
    recent = psc_cutoff(12)
    corporate = PSC.objects.filter(
        company_id=OuterRef("pk"),
        kind=CORPORATE_PSC_KIND,
        ceased=False,
        notified_on__gte=recent,
    )
    return queryset.filter(Exists(corporate))


def _filter_psc_flip(queryset):
    cutoff = psc_cutoff()
    ceased_individual = PSC.objects.filter(
        company_id=OuterRef("pk"),
        kind=INDIVIDUAL_PSC_KIND,
        ceased=True,
        ceased_on__gte=cutoff,
    )
    new_corporate = PSC.objects.filter(
        company_id=OuterRef("pk"),
        kind=CORPORATE_PSC_KIND,
        ceased=False,
        notified_on__gte=cutoff,
    )
    return queryset.filter(Exists(ceased_individual)).filter(Exists(new_corporate))


def _filter_director_age_under(queryset, max_age):
    ref_year = timezone.localdate().year
    min_birth_year = ref_year - max_age
    young_officer = Officer.objects.filter(
        company_id=OuterRef("pk"),
        resigned_on__isnull=True,
        date_of_birth_year__gt=min_birth_year,
    )
    return queryset.filter(Exists(young_officer))


def _filter_all_directors_over(queryset, min_age):
    ref_year = timezone.localdate().year
    max_birth_year = ref_year - min_age - 1
    young_officer = Officer.objects.filter(
        company_id=OuterRef("pk"),
        resigned_on__isnull=True,
        date_of_birth_year__gt=max_birth_year,
    )
    has_officer = Officer.objects.filter(
        company_id=OuterRef("pk"),
        resigned_on__isnull=True,
        date_of_birth_year__isnull=False,
    )
    return queryset.filter(Exists(has_officer)).exclude(Exists(young_officer))


def apply_signal_filters(queryset, signal_filters):
    if signal_filters["outstanding_charges"]:
        queryset = _filter_outstanding_charges(queryset)
    if signal_filters["charge_since"]:
        queryset = _filter_charge_since(queryset, signal_filters["charge_since"])
    if signal_filters["holder_contains"]:
        queryset = _filter_holder_contains(queryset, signal_filters["holder_contains"])
    if signal_filters["psc_since"]:
        queryset = _filter_psc_since(queryset, signal_filters["psc_since"])
    if signal_filters["new_corporate_psc"]:
        queryset = _filter_new_corporate_psc(queryset)
    if signal_filters["psc_flip"]:
        queryset = _filter_psc_flip(queryset)
    if signal_filters["director_age_under"] is not None:
        queryset = _filter_director_age_under(queryset, signal_filters["director_age_under"])
    if signal_filters["all_directors_over"] is not None:
        queryset = _filter_all_directors_over(queryset, signal_filters["all_directors_over"])
    if signal_filters["acquisition_signal"]:
        cutoff = psc_cutoff(12)
        recent_corporate = PSC.objects.filter(
            company_id=OuterRef("pk"),
            kind=CORPORATE_PSC_KIND,
            ceased=False,
            notified_on__gte=cutoff,
        )
        ceased_individual = PSC.objects.filter(
            company_id=OuterRef("pk"),
            kind=INDIVIDUAL_PSC_KIND,
            ceased=True,
            ceased_on__gte=psc_cutoff(),
        )
        new_corporate = PSC.objects.filter(
            company_id=OuterRef("pk"),
            kind=CORPORATE_PSC_KIND,
            ceased=False,
            notified_on__gte=psc_cutoff(),
        )
        queryset = queryset.filter(
            Q(Exists(recent_corporate))
            | (Q(Exists(ceased_individual)) & Q(Exists(new_corporate)))
        )
    if signal_filters["accounts_overdue"]:
        queryset = queryset.filter(accounts_overdue=True)
    if signal_filters["postcode"]:
        queryset = queryset.filter(registered_postal_code__icontains=signal_filters["postcode"])
    if signal_filters["region"]:
        queryset = queryset.filter(
            Q(registered_region__icontains=signal_filters["region"])
            | Q(registered_locality__icontains=signal_filters["region"])
        )
    return queryset


def _charges_for_scope(holder_filters):
    charge_qs = Charge.objects.filter(company_id=OuterRef("pk"))
    if holder_filters:
        charge_qs = charge_qs.filter(persons_entitled__id__in=holder_filters)
    return charge_qs


def apply_charge_activity_filter(queryset, activity, holder_filters):
    if activity == "active":
        active_charges = _charges_for_scope(holder_filters).filter(active_charge_q())
        return queryset.filter(Exists(active_charges))
    if activity == "inactive":
        active_charges = _charges_for_scope(holder_filters).filter(active_charge_q())
        return queryset.exclude(Exists(active_charges))
    return queryset


def apply_activity_filter(queryset, activity):
    if activity == "active":
        return queryset.filter(company_status__icontains="active")
    if activity == "inactive":
        return queryset.exclude(company_status__icontains="active")
    return queryset


def is_charge_company_view(holder_filters, has_charges):
    return bool(holder_filters or has_charges)


def _filter_by_holders(queryset, holder_ids):
    if not holder_ids:
        return queryset
    linked_charge = Charge.objects.filter(
        company_id=OuterRef("pk"),
        persons_entitled__id__in=holder_ids,
    )
    return queryset.filter(Exists(linked_charge))


def _filter_has_charges(queryset):
    linked_charge = Charge.objects.filter(company_id=OuterRef("pk"))
    return queryset.filter(Exists(linked_charge))


def _apply_search(queryset, search_query):
    if not search_query:
        return queryset
    return queryset.filter(
        Q(company_name__icontains=search_query) | Q(company_number__icontains=search_query)
    )


def charge_scope_activity_counts(queryset, holder_filters=None):
    """Single aggregate: total companies + how many have an outstanding charge."""
    active_charges = _charges_for_scope(holder_filters).filter(active_charge_q())
    stats = queryset.aggregate(
        total=Count("pk"),
        active=Count("pk", filter=Q(Exists(active_charges))),
    )
    total = stats["total"] or 0
    active = stats["active"] or 0
    return total, active, total - active


def _holder_count_subquery(*, active_only=False, companies=False):
    charges = Charge.objects.filter(persons_entitled=OuterRef("pk"))
    if active_only:
        charges = charges.filter(active_charge_q())
    count_field = "company_id" if companies else "pk"
    return (
        charges.order_by()
        .values("persons_entitled")
        .annotate(_c=Count(count_field, distinct=True))
        .values("_c")[:1]
    )


def _annotate_holder_counts(queryset, *, need_company=True, need_active_company=False):
    annotations = {
        "charge_count": Coalesce(
            Subquery(_holder_count_subquery(), output_field=IntegerField()),
            0,
        ),
    }
    if need_company:
        annotations["company_count"] = Coalesce(
            Subquery(
                _holder_count_subquery(companies=True),
                output_field=IntegerField(),
            ),
            0,
        )
    if need_active_company:
        annotations["active_company_count"] = Coalesce(
            Subquery(
                _holder_count_subquery(companies=True, active_only=True),
                output_field=IntegerField(),
            ),
            0,
        )
    return queryset.annotate(**annotations)


def build_charge_holders_queryset(request):
    search_query = request.GET.get("q", "").strip()
    activity = parse_activity_filter(request)
    group_holders = parse_bool_param(request, "group")

    has_any_charge = Exists(Charge.objects.filter(persons_entitled=OuterRef("pk")))
    has_active_charge = Exists(
        Charge.objects.filter(persons_entitled=OuterRef("pk")).filter(active_charge_q())
    )

    queryset = PersonEntitled.objects.only(*HOLDER_LIST_FIELDS).filter(has_any_charge)

    if activity == "active":
        queryset = queryset.filter(has_active_charge)
        queryset = _annotate_holder_counts(
            queryset, need_company=False, need_active_company=True
        )
    elif activity == "inactive":
        queryset = queryset.exclude(has_active_charge)
        queryset = _annotate_holder_counts(
            queryset, need_company=True, need_active_company=False
        )
    else:
        queryset = _annotate_holder_counts(
            queryset, need_company=True, need_active_company=False
        )

    if search_query:
        queryset = queryset.filter(name__icontains=search_query)

    return queryset.order_by("name"), search_query, activity, group_holders


def invalidate_facet_counts_cache():
    cache.delete(FACET_COUNTS_CACHE_KEY)


def global_facet_counts():
    try:
        cached = cache.get(FACET_COUNTS_CACHE_KEY)
        if cached is not None:
            return cached
    except Exception:
        cached = None

    status_counts = list(
        Company.objects.values("company_status")
        .annotate(count=Count("company_number"))
        .order_by("company_status")
    )
    account_counts = list(
        Company.objects.values("accounts_category")
        .annotate(count=Count("company_number"))
        .order_by("accounts_category")
    )
    payload = {"status": status_counts, "accounts": account_counts}
    try:
        cache.set(FACET_COUNTS_CACHE_KEY, payload, FACET_COUNTS_CACHE_SECONDS)
    except Exception:
        pass
    return payload


def facet_counts_for_scope(sidebar_scope):
    status_counts = list(
        sidebar_scope.values("company_status")
        .annotate(count=Count("company_number"))
        .order_by("company_status")
    )
    account_counts = list(
        sidebar_scope.values("accounts_category")
        .annotate(count=Count("company_number"))
        .order_by("accounts_category")
    )
    return {"status": status_counts, "accounts": account_counts}


def build_company_queryset(request):
    search_query = request.GET.get("q", "").strip()
    sic_query = parse_sic_query(request)
    status_filters = [value for value in request.GET.getlist("status") if value]
    accounts_filters = [value for value in request.GET.getlist("accounts_category") if value]
    holder_filters = parse_holder_filters(request)
    has_charges = parse_has_charges(request)
    activity = parse_activity_filter(request)
    signal_filters = parse_signal_filters(request)
    sort = request.GET.get("sort", "").strip().lower()
    charge_view = is_charge_company_view(holder_filters, has_charges)
    matched_sic_codes = find_matching_sic_codes(sic_query) if sic_query else []

    queryset = _apply_search(Company.objects.all(), search_query)

    if sic_query:
        if not matched_sic_codes:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(company_sic_filter_q(matched_sic_codes))

    queryset = apply_signal_filters(queryset, signal_filters)

    if holder_filters:
        queryset = _filter_by_holders(queryset, holder_filters)
    elif has_charges:
        queryset = _filter_has_charges(queryset)

    charge_scope = queryset if charge_view else None

    if charge_view and activity:
        queryset = apply_charge_activity_filter(queryset, activity, holder_filters)
    elif len(status_filters) == 1 and status_filters[0].lower() == "active":
        queryset = queryset.filter(company_status__icontains="active")
    elif len(status_filters) == 1 and status_filters[0].lower() == "dissolved":
        queryset = queryset.filter(company_status__icontains="dissolved")
    elif status_filters:
        queryset = queryset.filter(company_status__in=status_filters)

    if accounts_filters:
        queryset = queryset.filter(accounts_category__in=accounts_filters)

    if sort in {"charges", "psc"}:
        queryset = db_annotate_list_signals(queryset)

    if sort == "newest":
        queryset = queryset.order_by("-created_at", "company_number")
    elif sort == "incorporated":
        queryset = queryset.order_by("-date_of_creation", "company_name", "company_number")
    elif sort == "charges":
        queryset = queryset.order_by(
            "-outstanding_charge_count",
            "-latest_outstanding_charge",
            "company_name",
        )
    elif sort == "psc":
        queryset = queryset.order_by("-psc_latest_change", "company_name")
    else:
        queryset = queryset.order_by("company_name", "company_number")

    selected_holders = list(
        PersonEntitled.objects.filter(id__in=holder_filters)
        .only("id", "name")
        .order_by("name")
    ) if holder_filters else []

    return queryset, {
        "search_query": search_query,
        "sic_query": sic_query,
        "matched_sic_codes": matched_sic_codes,
        "holder_filters": holder_filters,
        "selected_holders": selected_holders,
        "has_charges": has_charges or bool(holder_filters),
        "activity": activity,
        "is_charge_view": charge_view,
        "charge_scope": charge_scope,
        "signal_filters": signal_filters,
    }


OFFICER_LIST_FIELDS = (
    "officer_id",
    "name",
    "officer_role",
    "appointed_on",
    "resigned_on",
    "nationality",
    "occupation",
    "company_id",
    "company__company_name",
)


def build_officers_queryset(request):
    search_query = request.GET.get("q", "").strip()
    activity = parse_activity_filter(request)
    queryset = Officer.objects.select_related("company").only(*OFFICER_LIST_FIELDS)

    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query)
            | Q(company__company_name__icontains=search_query)
            | Q(company_id__icontains=search_query)
        )

    if activity == "active":
        queryset = queryset.filter(resigned_on__isnull=True)
    elif activity == "inactive":
        queryset = queryset.filter(resigned_on__isnull=False)

    return queryset.order_by("name", "company__company_name", "officer_id"), search_query, activity


def query_has_list_scope(request, filter_meta, *, status_filters=None, accounts_filters=None):
    """True when filters narrow the search — avoids full-table scans on small DB plans."""
    status_filters = status_filters if status_filters is not None else request.GET.getlist("status")
    accounts_filters = (
        accounts_filters
        if accounts_filters is not None
        else request.GET.getlist("accounts_category")
    )
    if filter_meta.get("search_query"):
        return True
    if filter_meta.get("sic_query"):
        return True
    if filter_meta.get("holder_filters"):
        return True
    if filter_meta.get("has_charges"):
        return True
    if filter_meta.get("activity"):
        return True
    if request.GET.get("facet", "").strip().lower() == "sic":
        return True
    if status_filters:
        return True
    if accounts_filters:
        return True
    signal = filter_meta.get("signal_filters") or {}
    if signal.get("outstanding_charges"):
        return True
    if signal.get("charge_since"):
        return True
    if signal.get("holder_contains"):
        return True
    if signal.get("psc_since"):
        return True
    if signal.get("new_corporate_psc"):
        return True
    if signal.get("psc_flip"):
        return True
    if signal.get("director_age_under") is not None:
        return True
    if signal.get("all_directors_over") is not None:
        return True
    if signal.get("acquisition_signal"):
        return True
    if signal.get("accounts_overdue"):
        return True
    if signal.get("postcode"):
        return True
    if signal.get("region"):
        return True
    return False
