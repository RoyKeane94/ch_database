from datetime import datetime

from .models import Company

# Expected CSV columns (CompanyNumber is the only required header)
CSV_COLUMNS = [
    "CompanyName",
    "CompanyNumber",
    "CompanyCategory",
    "CompanyStatus",
    "CountryOfOrigin",
    "IncorporationDate",
    "Accounts.AccountRefDay",
    "Accounts.AccountRefMonth",
    "Accounts.LastMadeUpDate",
    "Accounts.AccountCategory",
]

CSV_REQUIRED_COLUMNS = {"CompanyNumber"}
CSV_COLUMN_MAP = {
    "CompanyName": "company_name",
    "CompanyCategory": "company_category",
    "CompanyStatus": "company_status",
    "CountryOfOrigin": "country_of_origin",
    "IncorporationDate": "date_of_creation",
    "Accounts.AccountRefDay": "accounts_ref_day",
    "Accounts.AccountRefMonth": "accounts_ref_month",
    "Accounts.LastMadeUpDate": "accounts_last_made_up",
    "Accounts.AccountCategory": "accounts_category",
}
DATE_FIELDS = {"date_of_creation", "accounts_last_made_up"}
INT_FIELDS = {"accounts_ref_day", "accounts_ref_month"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y")


def normalize_company_number(value):
    return (value or "").strip().zfill(8)


def normalize_csv_row(raw_row):
    normalized = {}
    for key, value in raw_row.items():
        column = (key or "").strip()
        if isinstance(value, str):
            normalized[column] = value.strip()
        else:
            normalized[column] = value
    return normalized


def parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD or DD/MM/YYYY.")


def parse_int(value, field_name):
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    if value.endswith(".0"):
        value = value[:-2]
    if not value.isdigit():
        raise ValueError(f"Invalid integer '{value}' for {field_name}.")
    return int(value)


def parse_accounts_ref_day(value):
    day = parse_int(value, "accounts_ref_day")
    if day is None:
        return None
    if not 1 <= day <= 31:
        raise ValueError(f"Invalid accounts ref day '{day}'. Must be between 1 and 31.")
    return day


def parse_accounts_ref_month(value):
    month = parse_int(value, "accounts_ref_month")
    if month is None:
        return None
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid accounts ref month '{month}'. Must be between 1 and 12.")
    return month


def normalize_accounting_dates(parsed_data):
    """Validate ref day/month and derive them from last made up date when missing."""
    ref_day = parsed_data.get("accounts_ref_day")
    ref_month = parsed_data.get("accounts_ref_month")
    last_made_up = parsed_data.get("accounts_last_made_up")

    if ref_day is not None and ref_month is not None:
        return parsed_data

    if last_made_up is None:
        return parsed_data

    if ref_day is None:
        parsed_data["accounts_ref_day"] = last_made_up.day
    if ref_month is None:
        parsed_data["accounts_ref_month"] = last_made_up.month

    return parsed_data


def parse_company_row(raw_row):
    raw_row = normalize_csv_row(raw_row)
    company_number = normalize_company_number(raw_row.get("CompanyNumber"))
    if not company_number or company_number == "00000000":
        return None

    parsed_data = {
        "company_number": company_number,
    }

    for csv_column, model_field in CSV_COLUMN_MAP.items():
        raw_value = raw_row.get(csv_column, "")
        if model_field in DATE_FIELDS:
            parsed_data[model_field] = parse_date(raw_value) if raw_value else None
        elif model_field == "accounts_ref_day":
            parsed_data[model_field] = parse_accounts_ref_day(raw_value)
        elif model_field == "accounts_ref_month":
            parsed_data[model_field] = parse_accounts_ref_month(raw_value)
        else:
            parsed_data[model_field] = raw_value or ""

    parsed_data = normalize_accounting_dates(parsed_data)
    return Company(**parsed_data)


def ensure_required_columns(fieldnames):
    fieldnames = [(name or "").strip() for name in (fieldnames or [])]
    missing_columns = CSV_REQUIRED_COLUMNS - set(fieldnames)
    if missing_columns:
        missing_str = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required CSV column(s): {missing_str}")
