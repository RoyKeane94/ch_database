from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView

from . import error_views, exports, views

app_name = "core"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="core:company_list", permanent=False)),
    path("companies/", views.company_list, name="company_list"),
    path("browse/", RedirectView.as_view(pattern_name="core:company_list", permanent=False)),
    path("upload/", views.upload_csv, name="upload_csv"),
    path("help/", views.help_page, name="help"),
    path("stats/", views.charge_holders_page, name="stats"),
    path("stats/export.<str:export_format>/", exports.export_charge_holders, name="export_charge_holders"),
    path("companies/export.<str:export_format>/", exports.export_companies, name="export_companies"),
    path("directors/", views.directors_page, name="directors"),
    path(
        "charges/",
        RedirectView.as_view(pattern_name="core:stats", permanent=False),
        name="charge_holders",
    ),
    path("holidays-not-included/", views.holidays_page, name="holidays"),
    path("health/", views.health_check, name="health"),
    path("api/sync-status/", views.sync_status_api, name="sync_status_api"),
    path("company/<str:company_number>/", views.company_detail, name="company_detail"),
]

if settings.DEBUG:
    urlpatterns.append(
        path("test-error/<str:code>/", error_views.error_preview, name="error_preview"),
    )
