from django.contrib import admin

from .models import Charge, Company, PSC, PersonEntitled


class ChargeInline(admin.TabularInline):
    model = Charge
    extra = 0
    readonly_fields = ("charge_code",)
    filter_horizontal = ("persons_entitled",)


class PSCInline(admin.TabularInline):
    model = PSC
    extra = 0
    readonly_fields = ("psc_id",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "company_number",
        "company_name",
        "company_status",
        "company_type",
        "needs_enrichment",
        "last_fetched_at",
    )
    list_filter = ("company_status", "company_type", "needs_enrichment", "accounts_overdue")
    search_fields = ("company_number", "company_name")
    inlines = (ChargeInline, PSCInline)


@admin.register(PersonEntitled)
class PersonEntitledAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = (
        "charge_code",
        "company",
        "status",
        "charge_number",
        "created_on",
        "last_fetched_at",
    )
    list_filter = ("status",)
    search_fields = ("charge_code", "company__company_number", "company__company_name")
    filter_horizontal = ("persons_entitled",)


@admin.register(PSC)
class PSCAdmin(admin.ModelAdmin):
    list_display = ("psc_id", "company", "name", "kind", "ceased", "notified_on", "ceased_on")
    list_filter = ("kind", "ceased")
    search_fields = ("psc_id", "company__company_number", "company__company_name", "name")
