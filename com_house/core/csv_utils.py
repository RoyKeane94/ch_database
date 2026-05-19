from datetime import datetime

from .models import Company


CSV_REQUIRED_COLUMNS = {"CompanyNumber"}
CSV_COLUMN_MAP = {
    "CompanyName": "company_name",
    "CompanyCategory": "company_category",
    "CompanyStatus": "company_status",
    "CountryOfOrigin": "country_of_origin",
    "IncorporationDate": "incorporated_on",
    "Accounts.AccountRefDay": "accounts_ref_day",
    "Accounts.AccountRefMonth": "accounts_ref_month",
    "Accounts.LastMadeUpDate": "accounts_last_made_up",
    "Accounts.AccountCategory": "accounts_category",
}
DATE_FIELDS = {"incorporated_on", "accounts_last_made_up"}
INT_FIELDS = {"accounts_ref_day", "accounts_ref_month"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


def normalize_company_number(value):
    return (value or "").strip().zfill(8)


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD or DD/MM/YYYY.")


def parse_int(value, field_name):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    if not value.isdigit():
        raise ValueError(f"Invalid integer '{value}' for {field_name}.")
    return int(value)


def parse_company_row(raw_row):
    company_number = normalize_company_number(raw_row.get("CompanyNumber"))
    if not company_number or company_number == "00000000":
        return None

    parsed_data = {
        "company_number": company_number,
    }

    for csv_column, model_field in CSV_COLUMN_MAP.items():
        raw_value = raw_row.get(csv_column, "")
        raw_value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if model_field in DATE_FIELDS:
            parsed_data[model_field] = parse_date(raw_value) if raw_value else None
        elif model_field in INT_FIELDS:
            parsed_data[model_field] = parse_int(raw_value, model_field)
        else:
            parsed_data[model_field] = raw_value or ""

    return Company(**parsed_data)


def ensure_required_columns(fieldnames):
    fieldnames = fieldnames or []
    missing_columns = CSV_REQUIRED_COLUMNS - set(fieldnames)
    if missing_columns:
        missing_str = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required CSV column(s): {missing_str}")
