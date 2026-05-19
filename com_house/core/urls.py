from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.company_list, name="company_list"),
    path("upload/", views.upload_csv, name="upload_csv"),
    path("company/<str:company_number>/", views.company_detail, name="company_detail"),
]
