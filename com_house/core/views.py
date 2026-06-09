import csv
from io import TextIOWrapper
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .csv_utils import ensure_required_columns, parse_company_row
from .models import Company

UPLOAD_MAX_ROWS = 10_000
UPLOAD_CHUNK_SIZE = 1_000


def _company_initials(company):
    name = (company.company_name or "").strip()
    if not name:
        return company.company_number[:2]
    words = [word for word in name.split() if word]
    if len(words) == 1:
        return words[0][:2].upper()
    return f"{words[0][0]}{words[1][0]}".upper()


def _build_filter_url(base_params, **updates):
    params = dict(base_params)
    for key, value in updates.items():
        if value:
            params[key] = value
        else:
            params.pop(key, None)
    if not params:
        return "?"
    return f"?{urlencode(params)}"


def company_list(request):
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("company_status", "").strip()
    accounts_category_filter = request.GET.get("accounts_category", "").strip()

    sidebar_scope = Company.objects.all()
    if search_query:
        sidebar_scope = sidebar_scope.filter(
            Q(company_name__icontains=search_query) | Q(company_number__icontains=search_query)
        )

    queryset = sidebar_scope

    base_params = {}
    if search_query:
        base_params["q"] = search_query
    if status_filter:
        base_params["company_status"] = status_filter
    if accounts_category_filter:
        base_params["accounts_category"] = accounts_category_filter

    if status_filter:
        queryset = queryset.filter(company_status=status_filter)
    if accounts_category_filter:
        queryset = queryset.filter(accounts_category=accounts_category_filter)

    queryset = queryset.order_by("company_name", "company_number")

    total_count = queryset.count()
    paginator = Paginator(queryset, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    for company in page_obj.object_list:
        company.ui_initials = _company_initials(company)
        company.ui_status_strip = {
            "active": "border-l-blue",
            "dissolved": "border-l-slate",
            "liquidation": "border-l-slate",
        }.get((company.company_status or "").lower(), "border-l-rule")

    status_counts_raw = (
        sidebar_scope.values("company_status")
        .annotate(count=Count("company_number"))
        .order_by("company_status")
    )
    status_counts = [
        {
            "label": item["company_status"] or "Unknown",
            "value": item["company_status"] or "",
            "count": item["count"],
            "active": (status_filter == (item["company_status"] or "")),
            "url": _build_filter_url(base_params, company_status=item["company_status"] or ""),
        }
        for item in status_counts_raw
    ]

    account_counts_raw = (
        sidebar_scope.values("accounts_category")
        .annotate(count=Count("company_number"))
        .order_by("accounts_category")
    )
    account_counts = [
        {
            "label": item["accounts_category"] or "Unknown",
            "value": item["accounts_category"] or "",
            "count": item["count"],
            "active": (accounts_category_filter == (item["accounts_category"] or "")),
            "url": _build_filter_url(
                base_params, accounts_category=item["accounts_category"] or ""
            ),
        }
        for item in account_counts_raw
    ]

    context = {
        "page_obj": page_obj,
        "total_count": total_count,
        "search_query": search_query,
        "status_filter": status_filter,
        "accounts_category_filter": accounts_category_filter,
        "status_options": Company.objects.exclude(company_status="").values_list(
            "company_status", flat=True
        ).distinct(),
        "accounts_category_options": Company.objects.exclude(
            accounts_category=""
        ).values_list("accounts_category", flat=True).distinct(),
        "status_counts": status_counts,
        "account_counts": account_counts,
        "clear_filters_url": _build_filter_url({"q": search_query} if search_query else {}),
    }
    return render(request, "core/company_list.html", context)


def company_detail(request, company_number):
    company = get_object_or_404(Company, pk=company_number)
    context = {
        "company": company,
        "charges": company.charges.all(),
        "psc_events": company.psc_events.all(),
    }
    return render(request, "core/company_detail.html", context)


@require_http_methods(["GET", "POST"])
def upload_csv(request):
    if request.method == "GET":
        return render(request, "core/upload.html")

    upload_file = request.FILES.get("file")
    if not upload_file:
        messages.error(request, "Please select a CSV file.")
        return render(request, "core/upload.html")

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
                    "This file has more than 10,000 rows. "
                    "Use `python manage.py import_csv <path>` for large uploads."
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
        messages.error(request, "Unable to decode file. Please upload a UTF-8 CSV.")
        return render(request, "core/upload.html")
    except ValueError as exc:
        messages.error(request, str(exc))
        return render(request, "core/upload.html")

    existing_numbers = set(
        Company.objects.filter(company_number__in=seen_numbers).values_list(
            "company_number", flat=True
        )
    )
    to_create = [company for company in parsed_companies if company.company_number not in existing_numbers]

    for idx in range(0, len(to_create), UPLOAD_CHUNK_SIZE):
        Company.objects.bulk_create(
            to_create[idx : idx + UPLOAD_CHUNK_SIZE],
            ignore_conflicts=True,
        )

    created_count = len(to_create)
    skipped_count = total_rows - created_count
    if duplicate_rows_in_file:
        skipped_count = max(skipped_count, len(existing_numbers) + duplicate_rows_in_file)

    messages.success(
        request,
        f"Upload complete. Created {created_count} companies, skipped {skipped_count}.",
    )
    return redirect("core:company_list")
