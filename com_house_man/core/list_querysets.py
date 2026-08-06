from django.core.cache import cache
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from core.models import Charge, Company, PersonEntitled
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
)

COMPANY_EXPORT_FIELDS = COMPANY_LIST_FIELDS + (
    "registered_postal_code",
)

HOLDER_LIST_FIELDS = (
    "id",
    "name",
)

FACET_COUNTS_CACHE_KEY = "company_facet_counts_v1"
FACET_COUNTS_CACHE_SECONDS = 120


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


def active_charge_q(prefix=""):
    if prefix and not prefix.endswith("__"):
        prefix = f"{prefix}__"
    return (
        Q(**{f"{prefix}satisfied_on__isnull": True})
        & ~Q(**{f"{prefix}status__icontains": "fully-satisfied"})
        & ~Q(**{f"{prefix}status__icontains": "fully satisfied"})
    )


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

    return queryset.order_by("name"), search_query, activity


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
    sort = request.GET.get("sort", "").strip().lower()
    charge_view = is_charge_company_view(holder_filters, has_charges)
    matched_sic_codes = find_matching_sic_codes(sic_query) if sic_query else []

    queryset = _apply_search(Company.objects.all(), search_query)

    if sic_query:
        if not matched_sic_codes:
            queryset = queryset.none()
        else:
            queryset = queryset.filter(company_sic_filter_q(matched_sic_codes))

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

    if sort == "newest":
        queryset = queryset.order_by("-created_at", "company_number")
    elif sort == "incorporated":
        queryset = queryset.order_by("-date_of_creation", "company_name", "company_number")
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
    }
