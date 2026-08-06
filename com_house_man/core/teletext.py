COMPANY_TYPE_LABELS = {
    "ltd": "Private limited",
    "plc": "PLC",
    "llp": "LLP",
    "limited-partnership": "Limited partnership",
    "private-unlimited": "Private unlimited",
    "private-limited-guarant-nsc": "Limited by guarantee",
    "oversea-company": "Overseas",
    "registered-overseas-entity": "Overseas entity",
}

STATUS_LABELS = {
    "active": ("Active", "status-active"),
    "dissolved": ("Dissolved", "status-dissolved"),
    "liquidation": ("Liquidation", "status-pending"),
    "administration": ("Administration", "status-pending"),
    "receivership": ("Receivership", "status-pending"),
}


def format_company_type(company):
    company_type = (company.company_type or "").strip().lower()
    if company_type:
        return COMPANY_TYPE_LABELS.get(company_type, company_type.replace("-", " ").title())

    category = (company.company_category or "").lower()
    if "limited liability partnership" in category or category == "llp":
        return "LLP"
    if "public limited" in category or "plc" in category:
        return "PLC"
    if "private limited" in category:
        return "Private limited"
    if category:
        return category.title()
    return "Unknown"


def format_status(company):
    status = (company.company_status or "").strip().lower()
    if status in STATUS_LABELS:
        return STATUS_LABELS[status]
    if status:
        return (status.replace("-", " ").title(), "status-pending")
    return ("Unknown", "status-pending")
