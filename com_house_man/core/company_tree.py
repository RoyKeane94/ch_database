from core.models import Company, PSC

CORPORATE_PSC_KIND = "corporate-entity-person-with-significant-control"
TREE_DEPTH = 2

KIND_LABELS = {
    "individual-person-with-significant-control": "Individual",
    "corporate-entity-person-with-significant-control": "Corporate entity",
    "legal-person-person-with-significant-control": "Legal person",
    "super-secure-person-with-significant-control": "Super secure",
}

ROLE_LABELS = {
    "controller": "Controller",
    "subject": "This company",
    "subsidiary": "Subsidiary",
}

PSC_TERMS = {
    "ownership-of-shares-25-to-50-percent": ("Shares", 1, "25–50%"),
    "ownership-of-shares-50-to-75-percent": ("Shares", 2, "50–75%"),
    "ownership-of-shares-75-to-100-percent": ("Shares", 3, "75–100%"),
    "voting-rights-25-to-50-percent": ("Voting rights", 1, "25–50%"),
    "voting-rights-50-to-75-percent": ("Voting rights", 2, "50–75%"),
    "voting-rights-75-to-100-percent": ("Voting rights", 3, "75–100%"),
    "right-to-appoint-and-remove-directors": ("Directors", None, "Can appoint and remove"),
    "significant-influence-or-control": ("Influence", None, "Significant influence"),
}


def format_psc_kind(kind):
    return KIND_LABELS.get(kind, (kind or "").replace("-", " ").title() or "—")


def control_terms(natures):
    """Map PSC natures_of_control into ctree gauge rows."""
    if not natures:
        return []

    terms = []
    seen_labels = set()
    for nature in natures:
        raw = (nature or "").strip().lower()
        if not raw:
            continue

        note = ""
        key = raw
        if key.endswith("-as-firm"):
            key = key[: -len("-as-firm")]
            note = "via firm"
        elif key.endswith("-as-trust"):
            key = key[: -len("-as-trust")]
            note = "via trust"

        mapped = PSC_TERMS.get(key)
        if not mapped:
            label = key.replace("-", " ").capitalize()
            if label in seen_labels:
                continue
            seen_labels.add(label)
            terms.append({"label": label, "band": None, "value": note or "Yes"})
            continue

        label, band, value = mapped
        if note:
            value = f"{value} ({note})"
        if label in seen_labels:
            for existing in terms:
                if existing["label"] == label and band and (
                    existing["band"] is None or band > existing["band"]
                ):
                    existing["band"] = band
                    existing["value"] = value
            continue
        seen_labels.add(label)
        terms.append({"label": label, "band": band, "value": value})
    return terms


def control_chips(natures):
    """Compact chip labels for the PSC list."""
    chips = []
    for term in control_terms(natures):
        if term["label"] in {"Shares", "Voting rights"}:
            chips.append(f"{term['label']} {term['value']}")
        else:
            chips.append(term["value"])
    return chips


def _company_map(numbers):
    if not numbers:
        return {}
    return {
        company.company_number: company
        for company in Company.objects.filter(company_number__in=numbers).only(
            "company_number",
            "company_name",
            "company_status",
        )
    }


def _resolve_controller_number(psc, name_index):
    if psc.controller_company_number:
        return psc.controller_company_number
    return name_index.get((psc.name or "").casefold(), "")


def _name_index_for(names):
    cleaned = {name for name in names if name}
    if not cleaned:
        return {}
    index = {}
    for company in Company.objects.filter(company_name__in=cleaned).only(
        "company_number",
        "company_name",
    ):
        index.setdefault(company.company_name.casefold(), company.company_number)
    missing = [name for name in cleaned if name.casefold() not in index]
    for name in missing:
        match = (
            Company.objects.filter(company_name__iexact=name)
            .only("company_number")
            .first()
        )
        if match:
            index[name.casefold()] = match.company_number
    return index


def _parent_pscs(company_number):
    return list(
        PSC.objects.filter(
            company_id=company_number,
            kind=CORPORATE_PSC_KIND,
            ceased=False,
        ).only(
            "psc_id",
            "name",
            "controller_company_number",
            "natures_of_control",
            "company_id",
        )
    )


def _child_pscs(company):
    by_number = list(
        PSC.objects.filter(
            controller_company_number=company.company_number,
            kind=CORPORATE_PSC_KIND,
            ceased=False,
        ).only(
            "psc_id",
            "name",
            "controller_company_number",
            "natures_of_control",
            "company_id",
        )
    )
    if not company.company_name:
        return by_number

    seen = {psc.psc_id for psc in by_number}
    by_name = PSC.objects.filter(
        name__iexact=company.company_name,
        kind=CORPORATE_PSC_KIND,
        ceased=False,
    ).only(
        "psc_id",
        "name",
        "controller_company_number",
        "natures_of_control",
        "company_id",
    )
    for psc in by_name:
        if psc.psc_id not in seen:
            by_number.append(psc)
            seen.add(psc.psc_id)
    return by_number


def _status_label(status, *, in_register):
    if not in_register:
        return "Not in register", False
    cleaned = (status or "").replace("-", " ").strip()
    if not cleaned:
        return "Unknown", False
    return cleaned.title(), "active" in cleaned.lower()


def _node(*, role, name, number="", status="", in_register=True, controls=None):
    status_label, is_active = _status_label(status, in_register=in_register)
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, role.title()),
        "name": name or number or "Unknown",
        "number": number or "",
        "status": status,
        "status_label": status_label,
        "is_active": is_active,
        "in_register": in_register,
        "url_number": number if (number and in_register) else "",
        "controls": controls or [],
        "children": [],
        "parents": [],
    }


def _node_from_company(company, *, role, controls=None):
    return _node(
        role=role,
        name=company.company_name or company.company_number,
        number=company.company_number,
        status=company.company_status,
        in_register=True,
        controls=controls,
    )


def _node_from_external(*, name, number, role, controls=None):
    return _node(
        role=role,
        name=name,
        number=number,
        status="",
        in_register=False,
        controls=controls,
    )


def _flatten_parent_chain(node):
    chain = []
    for parent in node.get("parents") or []:
        chain.extend(_flatten_parent_chain(parent))
    chain.append(node)
    return chain


def _append_branch(sequence, node):
    """Append node, then for each child: edge (how node controls child) + child branch."""
    sequence.append({"kind": "node", "node": {**node, "controls": []}})
    for child in node.get("children") or []:
        if child.get("controls"):
            sequence.append(
                {
                    "kind": "edge",
                    "role": child["role"],
                    "controls": child["controls"],
                }
            )
        _append_branch(sequence, child)


def build_ownership_tree(company, *, depth=TREE_DEPTH):
    """Build a flat ctree sequence: node, edge, node, edge, … top → bottom."""
    root = _node_from_company(company, role="subject")
    root["children"] = _build_descendants(
        company, depth=depth, seen={company.company_number}
    )
    parents = _build_ancestors(
        company, depth=depth, seen={company.company_number}
    )

    sequence = []
    primary = _flatten_parent_chain(parents[0]) if parents else []
    for parent in primary:
        sequence.append({"kind": "node", "node": {**parent, "controls": []}})
        if parent.get("controls"):
            sequence.append(
                {
                    "kind": "edge",
                    "role": parent["role"],
                    "controls": parent["controls"],
                }
            )

    _append_branch(sequence, root)

    entity_count = sum(1 for item in sequence if item["kind"] == "node")
    return {
        "root": root,
        "parents": parents,
        "sequence": sequence,
        "entity_count": entity_count,
        "has_links": bool(parents or root["children"]),
    }


def _build_descendants(company, *, depth, seen):
    if depth <= 0:
        return []

    child_pscs = _child_pscs(company)
    companies = _company_map([psc.company_id for psc in child_pscs])
    nodes = []
    for psc in child_pscs:
        child_company = companies.get(psc.company_id)
        controls = control_terms(psc.natures_of_control)
        if child_company is None:
            nodes.append(
                _node_from_external(
                    name=psc.company_id,
                    number=psc.company_id,
                    role="subsidiary",
                    controls=controls,
                )
            )
            continue
        if child_company.company_number in seen:
            continue
        node = _node_from_company(
            child_company, role="subsidiary", controls=controls
        )
        next_seen = seen | {child_company.company_number}
        node["children"] = _build_descendants(
            child_company, depth=depth - 1, seen=next_seen
        )
        nodes.append(node)
    nodes.sort(key=lambda item: (item["name"] or "").lower())
    return nodes


def _build_ancestors(company, *, depth, seen):
    if depth <= 0:
        return []

    parent_pscs = _parent_pscs(company.company_number)
    name_index = _name_index_for([psc.name for psc in parent_pscs])
    numbers = []
    resolved = []
    for psc in parent_pscs:
        number = _resolve_controller_number(psc, name_index)
        resolved.append((psc, number))
        if number:
            numbers.append(number)
    companies = _company_map(numbers)

    nodes = []
    for psc, number in resolved:
        controls = control_terms(psc.natures_of_control)
        parent_company = companies.get(number) if number else None
        if parent_company is None:
            nodes.append(
                _node_from_external(
                    name=psc.name,
                    number=number,
                    role="controller",
                    controls=controls,
                )
            )
            continue
        if parent_company.company_number in seen:
            continue
        node = _node_from_company(
            parent_company, role="controller", controls=controls
        )
        next_seen = seen | {parent_company.company_number}
        node["parents"] = _build_ancestors(
            parent_company, depth=depth - 1, seen=next_seen
        )
        nodes.append(node)
    nodes.sort(key=lambda item: (item["name"] or "").lower())
    return nodes
