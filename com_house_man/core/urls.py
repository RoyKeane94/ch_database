from django.urls import path
from django.views.generic import RedirectView

from . import views
from .cofax_live_api import cofax_live

app_name = "core"

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("companies/", views.company_list, name="company_list"),
    path("browse/", RedirectView.as_view(pattern_name="core:company_list", permanent=False)),
    path("upload/", views.upload_csv, name="upload_csv"),
    path("help/", views.help_page, name="help"),
    path("stats/", views.charge_holders_page, name="stats"),
    path("directors/", views.directors_page, name="directors"),
    path(
        "charges/",
        RedirectView.as_view(pattern_name="core:stats", permanent=False),
        name="charge_holders",
    ),
    path("holidays-not-included/", views.holidays_page, name="holidays"),
    path("health/", views.health_check, name="health"),
    path("api/sync-status/", views.sync_status_api, name="sync_status_api"),
    path("api/cofax/live/", cofax_live, name="cofax_live"),
    path("company/<str:company_number>/", views.company_detail, name="company_detail"),
]
