import csv
from io import TextIOWrapper
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from .company_tree import build_ownership_tree, control_chips, format_psc_kind
from .csv_utils import ensure_required_columns, parse_company_row
from .exports import export_query_string
from .list_querysets import (
    COMPANY_LIST_FIELDS,
    build_charge_holders_queryset,
    build_company_queryset,
    charge_scope_activity_counts,
    facet_counts_for_scope,
    global_facet_counts,
)
from .models import Company
from .sync_stats import get_sync_stats, invalidate_sync_stats_cache, sync_stats_payload
from .sic_lookup import company_sic_filter_q, sic_labels, sic_search_results, all_sic_codes
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


def company_list(request):
    status_filters = [value for value in request.GET.getlist("status") if value]
    accounts_filters = [value for value in request.GET.getlist("accounts_category") if value]
    sort = request.GET.get("sort", "").strip().lower()
    facet = request.GET.get("facet", "").strip().lower()

    queryset, filter_meta = build_company_queryset(request)
    search_query = filter_meta["search_query"]
    sic_query = filter_meta["sic_query"]
    matched_sic_codes = filter_meta["matched_sic_codes"]
    sic_matches = sic_search_results(sic_query) if sic_query else []
    if facet == "sic" and not sic_query:
        queryset = Company.objects.none()
    else:
        queryset = queryset.only(*COMPANY_LIST_FIELDS)
    sic_catalog = list(all_sic_codes()) if facet == "sic" else []
    holder_filters = filter_meta["holder_filters"]
    selected_holders = filter_meta["selected_holders"]
    has_charges = filter_meta["has_charges"]
    activity = filter_meta["activity"]
    is_charge_view = filter_meta["is_charge_view"]
    charge_scope = filter_meta["charge_scope"]

    charge_scope_total = charge_active_count = charge_inactive_count = 0
    if charge_scope is not None:
        charge_scope_total, charge_active_count, charge_inactive_count = (
            charge_scope_activity_counts(charge_scope, holder_filters)
        )

    paginator = Paginator(queryset, RESULTS_PER_PAGE)
    # Avoid a second COUNT when the page queryset matches the charge scope.
    if charge_scope is not None and not activity:
        paginator.count = charge_scope_total
    page_obj = paginator.get_page(request.GET.get("page"))
    total_count = paginator.count

    for company in page_obj.object_list:
        _annotate_company(company)

    status_options = []
    account_options = []
    if not is_charge_view and facet != "sic":
        use_global_facets = not search_query and not sic_query
        if use_global_facets:
            facet_data = global_facet_counts()
        else:
            sidebar_scope = Company.objects.all()
            if search_query:
                sidebar_scope = sidebar_scope.filter(
                    Q(company_name__icontains=search_query)
                    | Q(company_number__icontains=search_query)
                )
            if sic_query and matched_sic_codes:
                sidebar_scope = sidebar_scope.filter(
                    company_sic_filter_q(matched_sic_codes)
                )
            facet_data = facet_counts_for_scope(sidebar_scope)

        status_options = [
            {
                "label": (item["company_status"] or "unknown").upper(),
                "value": item["company_status"] or "",
                "count": item["count"],
                "checked": (item["company_status"] or "") in status_filters,
            }
            for item in facet_data["status"]
            if item["company_status"]
        ]
        account_options = [
            {
                "label": (item["accounts_category"] or "unknown").upper(),
                "value": item["accounts_category"] or "",
                "count": item["count"],
                "checked": (item["accounts_category"] or "") in accounts_filters,
            }
            for item in facet_data["accounts"]
            if item["accounts_category"]
        ]

    page_query = urlencode(
        {
            **({"q": search_query} if search_query else {}),
            **({"sic": sic_query} if sic_query else {}),
            **({"status": status_filters} if status_filters and not is_charge_view else {}),
            **({"accounts_category": accounts_filters} if accounts_filters else {}),
            **({"holder": [str(holder_id) for holder_id in holder_filters]} if holder_filters else {}),
            **({"has_charges": "1"} if has_charges and not holder_filters else {}),
            **({"activity": activity} if is_charge_view and activity else {}),
            **({"sort": sort} if sort else {}),
            **({"facet": facet} if facet else {}),
        },
        doseq=True,
    )

    activity_base = {
        **({"q": search_query} if search_query else {}),
        **({"sic": sic_query} if sic_query else {}),
        **({"holder": [str(holder_id) for holder_id in holder_filters]} if holder_filters else {}),
        **({"has_charges": "1"} if has_charges and not holder_filters else {}),
        **({"accounts_category": accounts_filters} if accounts_filters else {}),
        **({"sort": sort} if sort else {}),
    }
    activity_queries = {
        "all": urlencode(activity_base, doseq=True),
        "active": urlencode({**activity_base, "activity": "active"}, doseq=True),
        "inactive": urlencode({**activity_base, "activity": "inactive"}, doseq=True),
    }

    export_query = export_query_string(request)
    show_company_export = bool(holder_filters or has_charges)

    if is_charge_view:
        clear_params = {}
        if holder_filters:
            clear_params["holder"] = [str(holder_id) for holder_id in holder_filters]
        elif has_charges:
            clear_params["has_charges"] = "1"
    else:
        clear_params = {}
        if search_query:
            clear_params["q"] = search_query
        if facet == "sic":
            clear_params["facet"] = "sic"

    context = {
        "page_obj": page_obj,
        "total_count": total_count,
        "search_query": search_query,
        "sic_query": sic_query,
        "sic_matches": sic_matches,
        "sic_no_match": bool(sic_query and not matched_sic_codes),
        "sic_catalog": sic_catalog,
        "show_sic_catalog": facet == "sic",
        "status_filters": status_filters,
        "accounts_filters": accounts_filters,
        "holder_filters": holder_filters,
        "selected_holders": selected_holders,
        "has_charges": has_charges or bool(holder_filters),
        "activity": activity,
        "is_charge_view": is_charge_view,
        "charge_scope_total": charge_scope_total,
        "charge_active_count": charge_active_count,
        "charge_inactive_count": charge_inactive_count,
        "activity_queries": activity_queries,
        "sort": sort,
        "facet": facet,
        "status_options": status_options,
        "account_options": account_options,
        "clear_filters_url": _build_filter_url(clear_params),
        "page_query": page_query,
        "export_query": export_query,
        "show_company_export": show_company_export,
        "active_tab": "search",
    }
    return render(request, "core/company_list.html", context)


def company_detail(request, company_number):
    company = get_object_or_404(Company, pk=company_number)
    _annotate_company(company)
    charges = (
        company.charges.only(
            "charge_code",
            "company_id",
            "status",
            "created_on",
            "satisfied_on",
        )
        .prefetch_related("persons_entitled")
        .all()
    )
    pscs = list(
        company.pscs.only(
            "psc_id",
            "company_id",
            "name",
            "kind",
            "controller_company_number",
            "ceased",
            "ceased_on",
            "notified_on",
            "natures_of_control",
        )
    )
    for psc in pscs:
        psc.kind_label = format_psc_kind(psc.kind)
        psc.control_chips = control_chips(psc.natures_of_control)
    ownership_tree = build_ownership_tree(company)
    context = {
        "company": company,
        "charges": charges,
        "pscs": pscs,
        "ownership_tree": ownership_tree,
        "sic_labels": sic_labels(company.sic_codes),
        "active_tab": "search",
    }
    return render(request, "core/company_detail.html", context)


def help_page(request):
    return render(request, "core/help.html", {"active_tab": "help"})


def directors_page(request):
    return render(request, "core/directors.html", {"active_tab": "help"})


def charge_holders_page(request):
    selected_holders = [
        int(value)
        for value in request.GET.getlist("holder")
        if value.isdigit()
    ]

    queryset, search_query, activity = build_charge_holders_queryset(request)

    paginator = Paginator(queryset, HOLDERS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    total_count = paginator.count

    page_params = {}
    if search_query:
        page_params["q"] = search_query
    if activity:
        page_params["activity"] = activity
    for holder_id in selected_holders:
        page_params.setdefault("holder", []).append(str(holder_id))
    page_query = urlencode(page_params, doseq=True)

    activity_base = {}
    if search_query:
        activity_base["q"] = search_query
    if selected_holders:
        activity_base["holder"] = [str(holder_id) for holder_id in selected_holders]
    activity_queries = {
        "all": urlencode(activity_base, doseq=True),
        "active": urlencode({**activity_base, "activity": "active"}, doseq=True),
        "inactive": urlencode({**activity_base, "activity": "inactive"}, doseq=True),
    }

    companies_with_charges_url = reverse("core:company_list") + "?" + urlencode(
        {"has_charges": "1", **({"activity": activity} if activity else {})},
        doseq=True,
    )

    context = {
        "page_obj": page_obj,
        "total_count": total_count,
        "search_query": search_query,
        "selected_holders": selected_holders,
        "activity": activity,
        "activity_queries": activity_queries,
        "page_query": page_query,
        "companies_with_charges_url": companies_with_charges_url,
        "export_query": export_query_string(request),
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
