from io import BytesIO

from django.http import Http404, HttpResponse, JsonResponse
from django.utils.text import slugify
from openpyxl import Workbook

from core.list_querysets import (
    COMPANY_EXPORT_FIELDS,
    build_charge_holders_queryset,
    build_company_queryset,
)
from core.models import PersonEntitled

EXPORT_MAX_ROWS = 25_000

HOLDER_HEADERS = ["id", "name", "charge_count", "company_count"]
COMPANY_HEADERS = [
    "company_number",
    "company_name",
    "company_status",
    "company_type",
    "date_of_creation",
    "accounts_category",
    "registered_postal_code",
    "charge_holders",
    "companies_house_url",
]


def export_query_string(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _truncate_queryset(queryset):
    total = queryset.count()
    truncated = total > EXPORT_MAX_ROWS
    if truncated:
        queryset = queryset[:EXPORT_MAX_ROWS]
    return queryset, total, truncated


def _holder_rows(holders):
    return [
        [holder.id, holder.name, holder.charge_count, holder.company_count]
        for holder in holders
    ]


def _company_rows(companies, holder_filters):
    holder_names = {}
    if holder_filters:
        holder_names = dict(
            PersonEntitled.objects.filter(id__in=holder_filters).values_list("id", "name")
        )

    rows = []
    for company in companies:
        charge_holders = ", ".join(
            sorted(
                {
                    person.name
                    for charge in company.charges.all()
                    for person in charge.persons_entitled.all()
                    if person.name and (not holder_filters or person.id in holder_names)
                }
            )
        )

        rows.append(
            [
                company.company_number,
                company.company_name,
                company.company_status,
                company.company_type,
                company.date_of_creation.isoformat() if company.date_of_creation else "",
                company.accounts_category,
                company.registered_postal_code,
                charge_holders,
                company.companies_house_url,
            ]
        )
    return rows


def _json_attachment(payload, filename):
    response = JsonResponse(payload, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _excel_attachment(headers, rows, filename):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _holder_filename(search_query, ext):
    if search_query:
        slug = slugify(search_query)[:40] or "filtered"
        return f"charge-holders-{slug}.{ext}"
    return f"charge-holders.{ext}"


def _company_filename(meta, ext):
    if meta["selected_holders"]:
        if len(meta["selected_holders"]) == 1:
            slug = slugify(meta["selected_holders"][0].name)[:40] or "holder"
            return f"companies-{slug}.{ext}"
        return f"companies-{len(meta['selected_holders'])}-holders.{ext}"
    if meta["has_charges"]:
        return f"companies-with-charges.{ext}"
    return f"companies.{ext}"


def export_charge_holders(request, export_format):
    if export_format not in {"json", "xlsx"}:
        raise Http404

    queryset, search_query, _activity = build_charge_holders_queryset(request)
    holders, total, truncated = _truncate_queryset(queryset)
    rows = _holder_rows(holders)
    filename = _holder_filename(search_query, export_format)

    if export_format == "json":
        payload = {
            "export": "charge_holders",
            "search_query": search_query,
            "total": total,
            "exported": len(rows),
            "truncated": truncated,
            "rows": [
                {
                    "id": row[0],
                    "name": row[1],
                    "charge_count": row[2],
                    "company_count": row[3],
                }
                for row in rows
            ],
        }
        return _json_attachment(payload, filename)

    return _excel_attachment(HOLDER_HEADERS, rows, filename)


def export_companies(request, export_format):
    if export_format not in {"json", "xlsx"}:
        raise Http404

    queryset, meta = build_company_queryset(request)
    if not meta["holder_filters"] and not meta["has_charges"]:
        raise Http404

    companies, total, truncated = _truncate_queryset(
        queryset.only(*COMPANY_EXPORT_FIELDS).prefetch_related(
            "charges__persons_entitled"
        )
    )
    rows = _company_rows(companies, meta["holder_filters"])
    filename = _company_filename(meta, export_format)

    if export_format == "json":
        payload = {
            "export": "companies",
            "holder_ids": meta["holder_filters"],
            "holder_names": [holder.name for holder in meta["selected_holders"]],
            "has_charges": meta["has_charges"],
            "search_query": meta["search_query"],
            "total": total,
            "exported": len(rows),
            "truncated": truncated,
            "rows": [
                dict(zip(COMPANY_HEADERS, row, strict=True))
                for row in rows
            ],
        }
        return _json_attachment(payload, filename)

    return _excel_attachment(COMPANY_HEADERS, rows, filename)
