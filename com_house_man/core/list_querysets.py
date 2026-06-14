from django.db.models import Count, Q

from core.models import Company, PersonEntitled


def parse_holder_filters(request):
    return [int(value) for value in request.GET.getlist("holder") if value.isdigit()]


def parse_has_charges(request):
    return request.GET.get("has_charges", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_charge_holders_queryset(request):
    search_query = request.GET.get("q", "").strip()
    queryset = (
        PersonEntitled.objects.annotate(
            company_count=Count("charges__company", distinct=True),
            charge_count=Count("charges", distinct=True),
        )
        .filter(charge_count__gt=0)
        .order_by("name")
    )
    if search_query:
        queryset = queryset.filter(name__icontains=search_query)
    return queryset, search_query


def build_company_queryset(request):
    search_query = request.GET.get("q", "").strip()
    status_filters = [value for value in request.GET.getlist("status") if value]
    accounts_filters = [value for value in request.GET.getlist("accounts_category") if value]
    holder_filters = parse_holder_filters(request)
    has_charges = parse_has_charges(request)
    sort = request.GET.get("sort", "").strip().lower()

    queryset = Company.objects.all()
    if search_query:
        queryset = queryset.filter(
            Q(company_name__icontains=search_query) | Q(company_number__icontains=search_query)
        )

    if len(status_filters) == 1 and status_filters[0].lower() == "active":
        queryset = queryset.filter(company_status__icontains="active")
    elif len(status_filters) == 1 and status_filters[0].lower() == "dissolved":
        queryset = queryset.filter(company_status__icontains="dissolved")
    elif status_filters:
        queryset = queryset.filter(company_status__in=status_filters)

    if accounts_filters:
        queryset = queryset.filter(accounts_category__in=accounts_filters)

    if holder_filters:
        queryset = queryset.filter(
            charges__persons_entitled__id__in=holder_filters
        ).distinct()
    elif has_charges:
        queryset = queryset.filter(charges__isnull=False).distinct()

    if sort == "newest":
        queryset = queryset.order_by("-created_at", "company_number")
    elif sort == "incorporated":
        queryset = queryset.order_by("-date_of_creation", "company_name", "company_number")
    else:
        queryset = queryset.order_by("company_name", "company_number")

    selected_holders = list(
        PersonEntitled.objects.filter(id__in=holder_filters).order_by("name")
    ) if holder_filters else []

    return queryset, {
        "search_query": search_query,
        "holder_filters": holder_filters,
        "selected_holders": selected_holders,
        "has_charges": has_charges or bool(holder_filters),
    }
