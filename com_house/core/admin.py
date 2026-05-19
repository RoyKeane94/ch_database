from django.contrib import admin

from .models import Charge, Company, PSCEvent


class ChargeInline(admin.TabularInline):
    model = Charge
    extra = 0


class PSCEventInline(admin.TabularInline):
    model = PSCEvent
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "company_number",
        "company_name",
        "company_status",
        "accounts_category",
        "needs_enrichment",
        "last_enriched_at",
    )
    list_filter = ("company_status", "accounts_category", "needs_enrichment")
    search_fields = ("company_number", "company_name")
    inlines = (ChargeInline, PSCEventInline)


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("company", "holder_name", "charge_type", "status", "created_on")
    list_filter = ("status", "charge_type")
    search_fields = ("company__company_number", "company__company_name", "holder_name")


@admin.register(PSCEvent)
class PSCEventAdmin(admin.ModelAdmin):
    list_display = ("company", "psc_name", "psc_kind", "notified_on", "ceased_on")
    list_filter = ("psc_kind",)
    search_fields = ("company__company_number", "company__company_name", "psc_name")
