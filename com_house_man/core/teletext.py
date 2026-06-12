COMPANY_TYPE_LABELS = {
    "ltd": "PRIV LTD",
    "plc": "PLC",
    "llp": "LLP",
    "limited-partnership": "LTD PTNR",
    "private-unlimited": "PRIV UNL",
    "private-limited-guarant-nsc": "LTD GUAR",
    "oversea-company": "OVERSEAS",
    "registered-overseas-entity": "ROE",
}

STATUS_LABELS = {
    "active": ("ACTIVE", "tt-status-active"),
    "dissolved": ("DSLVD", "tt-status-dissolved"),
    "liquidation": ("LIQUD", "tt-status-dormant"),
    "administration": ("ADMIN", "tt-status-dormant"),
    "receivership": ("RCVR", "tt-status-dormant"),
}


def format_company_type(company):
    company_type = (company.company_type or "").strip().lower()
    if company_type:
        return COMPANY_TYPE_LABELS.get(company_type, company_type.upper().replace("-", " ")[:10])

    category = (company.company_category or "").lower()
    if "limited liability partnership" in category or category == "llp":
        return "LLP"
    if "public limited" in category or "plc" in category:
        return "PLC"
    if "private limited" in category:
        return "PRIV LTD"
    if category:
        return category.upper()[:10]
    return "UNKNOWN"


def format_status(company):
    status = (company.company_status or "").strip().lower()
    if status in STATUS_LABELS:
        return STATUS_LABELS[status]
    if status:
        return (status.upper()[:6], "tt-status-dormant")
    return ("UNKNOWN", "tt-status-dormant")
