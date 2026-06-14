import csv
from io import TextIOWrapper
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from .csv_utils import ensure_required_columns, parse_company_row
from .models import Company, PersonEntitled
from .sync_stats import get_sync_stats, invalidate_sync_stats_cache, sync_stats_payload
from .teletext import format_company_type, format_status

UPLOAD_MAX_ROWS = 10_000
UPLOAD_CHUNK_SIZE = 1_000
RESULTS_PER_PAGE = 20
HOLDERS_PER_PAGE = 50


def _build_filter_url(base_params, **updates):
    params = dict(base_params)
    for key, value in updates.items():
        if value:
            params[key] = value
        else:
            params.pop(key, None)
    if not params:
        return "?"
    return f"?{urlencode(params, doseq=True)}"


def _annotate_company(company):
    status_label, status_class = format_status(company)
    company.tt_status_label = status_label
    company.tt_status_class = status_class
    company.tt_type_label = format_company_type(company)
    return company


@require_GET
def sync_status_api(request):
    return JsonResponse(sync_stats_payload(get_sync_stats(use_cache=False)))


@require_GET
def health_check(request):
    from django.db import connection

    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_ok = False

    return JsonResponse(
        {
            "status": "ok",
            "database": "ok" if db_ok else "unavailable",
        }
    )


def _landing_context():
    return {
        "cofax_config": {
            "live_endpoint": reverse("core:cofax_live"),
            "urls": {
                "search": reverse("core:company_list"),
                "active": f"{reverse('core:company_list')}?status=active",
                "by_status": f"{reverse('core:company_list')}?facet=status",
                "dissolved": f"{reverse('core:company_list')}?status=dissolved",
                "upload": reverse("core:upload_csv"),
                "newest": f"{reverse('core:company_list')}?sort=newest",
                "account_type": f"{reverse('core:company_list')}?facet=account_type",
                "stats": reverse("core:stats"),
                "incorporated": f"{reverse('core:company_list')}?sort=incorporated",
                "directors": reverse("core:directors"),
                "charges": reverse("core:stats"),
                "with_charges": f"{reverse('core:company_list')}?has_charges=1",
                "index": reverse("core:stats"),
                "holidays": reverse("core:holidays"),
                "help": reverse("core:help"),
                "bbc_news": "https://www.bbc.co.uk/news",
                "bbc_weather": "https://www.bbc.co.uk/weather/2647428",
            },
        }
    }


def landing_page(request):
    return render(request, "core/landing.html", _landing_context())


def company_list(request):
    search_query = request.GET.get("q", "").strip()
    status_filters = [value for value in request.GET.getlist("status") if value]
    accounts_filters = [value for value in request.GET.getlist("accounts_category") if value]
    holder_filters = [
        int(value)
        for value in request.GET.getlist("holder")
        if value.isdigit()
    ]
    has_charges = request.GET.get("has_charges", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    sort = request.GET.get("sort", "").strip().lower()
    facet = request.GET.get("facet", "").strip().lower()

    sidebar_scope = Company.objects.all()
    if search_query:
        sidebar_scope = sidebar_scope.filter(
            Q(company_name__icontains=search_query) | Q(company_number__icontains=search_query)
        )

    queryset = sidebar_scope
    base_params = {}
    if search_query:
        base_params["q"] = search_query
    if sort:
        base_params["sort"] = sort
    if facet:
        base_params["facet"] = facet

    if len(status_filters) == 1 and status_filters[0].lower() == "active":
        queryset = queryset.filter(company_status__icontains="active")
        base_params["status"] = status_filters
    elif len(status_filters) == 1 and status_filters[0].lower() == "dissolved":
        queryset = queryset.filter(company_status__icontains="dissolved")
        base_params["status"] = status_filters
    elif status_filters:
        queryset = queryset.filter(company_status__in=status_filters)
        base_params["status"] = status_filters
    if accounts_filters:
        queryset = queryset.filter(accounts_category__in=accounts_filters)
        base_params["accounts_category"] = accounts_filters
    if holder_filters:
        queryset = queryset.filter(
            charges__persons_entitled__id__in=holder_filters
        ).distinct()
        base_params["holder"] = [str(holder_id) for holder_id in holder_filters]
    elif has_charges:
        queryset = queryset.filter(charges__isnull=False).distinct()
        base_params["has_charges"] = "1"

    if sort == "newest":
        queryset = queryset.order_by("-created_at", "company_number")
    elif sort == "incorporated":
        queryset = queryset.order_by("-date_of_creation", "company_name", "company_number")
    else:
        queryset = queryset.order_by("company_name", "company_number")

    total_count = queryset.count()
    paginator = Paginator(queryset, RESULTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    for company in page_obj.object_list:
        _annotate_company(company)

    status_counts_raw = (
        sidebar_scope.values("company_status")
        .annotate(count=Count("company_number"))
        .order_by("company_status")
    )
    status_options = [
        {
            "label": (item["company_status"] or "unknown").upper(),
            "value": item["company_status"] or "",
            "count": item["count"],
            "checked": (item["company_status"] or "") in status_filters,
        }
        for item in status_counts_raw
        if item["company_status"]
    ]

    account_counts_raw = (
        sidebar_scope.values("accounts_category")
        .annotate(count=Count("company_number"))
        .order_by("accounts_category")
    )
    account_options = [
        {
            "label": (item["accounts_category"] or "unknown").upper(),
            "value": item["accounts_category"] or "",
            "count": item["count"],
            "checked": (item["accounts_category"] or "") in accounts_filters,
        }
        for item in account_counts_raw
        if item["accounts_category"]
    ]

    page_query = urlencode(
        {
            **({"q": search_query} if search_query else {}),
            **({"status": status_filters} if status_filters else {}),
            **({"accounts_category": accounts_filters} if accounts_filters else {}),
            **({"holder": [str(holder_id) for holder_id in holder_filters]} if holder_filters else {}),
            **({"has_charges": "1"} if has_charges and not holder_filters else {}),
            **({"sort": sort} if sort else {}),
            **({"facet": facet} if facet else {}),
        },
        doseq=True,
    )

    selected_holders = list(
        PersonEntitled.objects.filter(id__in=holder_filters).order_by("name")
    ) if holder_filters else []

    context = {
        "page_obj": page_obj,
        "total_count": total_count,
        "search_query": search_query,
        "status_filters": status_filters,
        "accounts_filters": accounts_filters,
        "holder_filters": holder_filters,
        "selected_holders": selected_holders,
        "has_charges": has_charges or bool(holder_filters),
        "sort": sort,
        "facet": facet,
        "status_options": status_options,
        "account_options": account_options,
        "clear_filters_url": _build_filter_url({"q": search_query} if search_query else {}),
        "page_query": page_query,
        "active_tab": "search",
    }
    return render(request, "core/company_list.html", context)


def company_detail(request, company_number):
    company = get_object_or_404(Company, pk=company_number)
    _annotate_company(company)
    context = {
        "company": company,
        "charges": company.charges.prefetch_related("persons_entitled").all(),
        "pscs": company.pscs.all(),
        "active_tab": "search",
    }
    return render(request, "core/company_detail.html", context)


def help_page(request):
    return render(request, "core/help.html", {"active_tab": "help"})


def directors_page(request):
    return render(request, "core/directors.html", {"active_tab": "help"})


def charge_holders_page(request):
    search_query = request.GET.get("q", "").strip()
    selected_holders = [
        int(value)
        for value in request.GET.getlist("holder")
        if value.isdigit()
    ]

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

    total_count = queryset.count()
    paginator = Paginator(queryset, HOLDERS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    page_params = {}
    if search_query:
        page_params["q"] = search_query
    for holder_id in selected_holders:
        page_params.setdefault("holder", []).append(str(holder_id))
    page_query = urlencode(page_params, doseq=True)

    context = {
        "page_obj": page_obj,
        "total_count": total_count,
        "search_query": search_query,
        "selected_holders": selected_holders,
        "page_query": page_query,
        "companies_with_charges_url": f"{reverse('core:company_list')}?has_charges=1",
        "active_tab": "index",
    }
    return render(request, "core/charge_holders.html", context)


def holidays_page(request):
    return render(request, "core/holidays.html", {"active_tab": "help"})


@require_http_methods(["GET", "POST"])
def upload_csv(request):
    if request.method == "GET":
        return render(request, "core/upload.html", {"active_tab": "upload"})

    upload_file = request.FILES.get("file")
    if not upload_file:
        messages.error(request, "SELECT A CSV FILE BEFORE UPLOADING.")
        return render(request, "core/upload.html", {"active_tab": "upload"})

    try:
        csv_file = TextIOWrapper(upload_file.file, encoding="utf-8-sig")
        reader = csv.DictReader(csv_file)
        ensure_required_columns(reader.fieldnames)

        parsed_companies = []
        seen_numbers = set()
        total_rows = 0
        duplicate_rows_in_file = 0

        for row in reader:
            total_rows += 1
            if total_rows > UPLOAD_MAX_ROWS:
                raise ValueError(
                    "FILE EXCEEDS 10,000 ROWS. USE manage.py import_csv FOR LARGE FILES."
                )

            company = parse_company_row(row)
            if company is None:
                duplicate_rows_in_file += 1
                continue
            if company.company_number in seen_numbers:
                duplicate_rows_in_file += 1
                continue

            seen_numbers.add(company.company_number)
            parsed_companies.append(company)
    except UnicodeDecodeError:
        messages.error(request, "UNABLE TO DECODE FILE. USE UTF-8 CSV.")
        return render(request, "core/upload.html", {"active_tab": "upload"})
    except ValueError as exc:
        messages.error(request, str(exc))
        return render(request, "core/upload.html", {"active_tab": "upload"})

    existing_numbers = set(
        Company.objects.filter(company_number__in=seen_numbers).values_list(
            "company_number", flat=True
        )
    )
    to_create = [
        company for company in parsed_companies if company.company_number not in existing_numbers
    ]

    for idx in range(0, len(to_create), UPLOAD_CHUNK_SIZE):
        Company.objects.bulk_create(
            to_create[idx : idx + UPLOAD_CHUNK_SIZE],
            ignore_conflicts=True,
        )

    created_count = len(to_create)
    skipped_count = total_rows - created_count
    if duplicate_rows_in_file:
        skipped_count = max(skipped_count, len(existing_numbers) + duplicate_rows_in_file)

    if created_count:
        invalidate_sync_stats_cache()

    messages.success(
        request,
        f"UPLOAD COMPLETE. CREATED {created_count}. SKIPPED {skipped_count}.",
    )
    return redirect("core:company_list")
