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


OFFICER_ROLE_LABELS = {
    "director": "Director",
    "secretary": "Secretary",
    "nominee-director": "Nominee director",
    "nominee-secretary": "Nominee secretary",
    "corporate-director": "Corporate director",
    "corporate-secretary": "Corporate secretary",
    "corporate-nominee-director": "Corporate nominee director",
    "corporate-nominee-secretary": "Corporate nominee secretary",
    "llp-member": "LLP member",
    "llp-designated-member": "LLP designated member",
    "corporate-llp-member": "Corporate LLP member",
    "corporate-llp-designated-member": "Corporate LLP designated member",
}


def format_officer_role(role):
    key = (role or "").strip().lower()
    if key in OFFICER_ROLE_LABELS:
        return OFFICER_ROLE_LABELS[key]
    if key:
        return key.replace("-", " ").title()
    return "—"


def format_status(company):
    status = (company.company_status or "").strip().lower()
    if status in STATUS_LABELS:
        return STATUS_LABELS[status]
    if status:
        return (status.replace("-", " ").title(), "status-pending")
    return ("Unknown", "status-pending")
