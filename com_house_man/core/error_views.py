"""Ceefax-styled HTTP error handlers (standalone — no DB or context processors)."""

from django.shortcuts import render
from django.urls import reverse


def _error_context(request, *, page, code, headline, lines, hint="", status):
    return render(
        request,
        "ceefax_error.html",
        {
            "page": page,
            "error_code": code,
            "headline": headline,
            "lines": lines,
            "hint": hint,
            "path": request.path,
            "home_url": reverse("core:company_list"),
            "search_url": reverse("core:company_list"),
            "help_url": reverse("core:help"),
        },
        status=status,
    )


def page_not_found(request, exception):
    return _error_context(
        request,
        page="404",
        code="404",
        headline="SIGNAL LOST — PAGE NOT FOUND",
        lines=[
            "THE PAGE YOU REQUESTED HAS BEEN DISSOLVED",
            "OR WAS NEVER INCORPORATED AT COMPANIES HOUSE.",
            "OUR CEEFAX OPERATOR IS CHECKING THE INDEX CARDS.",
        ],
        hint="PRESS P100 BELOW TO RETURN TO COFAX",
        status=404,
    )


def server_error(request):
    return _error_context(
        request,
        page="500",
        code="500",
        headline="TRANSMISSION FAILURE",
        lines=[
            "THE COMPUTER HAS GONE ON HOLIDAY TO MALAGA.",
            "ENGINEERS ARE REFILLING THE TELETEXT CARTRIDGE.",
            "DO NOT ADJUST YOUR SET. NORMAL SERVICE WILL RESUME.",
        ],
        hint="IF THIS PERSISTS, TRY PAGE 101 (SEARCH) OR P100 (HOME)",
        status=500,
    )


def permission_denied(request, exception):
    return _error_context(
        request,
        page="403",
        code="403",
        headline="ACCESS DENIED",
        lines=[
            "THIS PAGE IS NOT INCLUDED IN YOUR CEEFAX SUBSCRIPTION.",
            "PLEASE CONTACT THE DUTY OPERATOR AT BBC MICRO SYSTEMS.",
        ],
        hint="RETURN TO P100 FOR AUTHORISED PAGES ONLY",
        status=403,
    )


def bad_request(request, exception):
    return _error_context(
        request,
        page="400",
        code="400",
        headline="BAD REQUEST — GARBLED SIGNAL",
        lines=[
            "YOUR REMOTE CONTROL SENT DATA WE CANNOT DECODE.",
            "PLEASE RETUNE AND TRY AGAIN.",
        ],
        hint="CHECK YOUR URL AND PRESS P100 TO START OVER",
        status=400,
    )


def error_preview(request, code):
    """Preview Ceefax error pages in development (DEBUG only)."""
    previews = {
        "400": lambda: bad_request(request, None),
        "403": lambda: permission_denied(request, None),
        "404": lambda: page_not_found(request, None),
        "500": lambda: server_error(request),
    }
    handler = previews.get(code)
    if handler is None:
        return page_not_found(request, None)
    return handler()
