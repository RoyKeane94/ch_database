import calendar

from django.db import models


class Company(models.Model):
    # From CSV
    company_number = models.CharField(max_length=8, primary_key=True)
    company_name = models.CharField(max_length=255, blank=True)
    company_category = models.CharField(max_length=100, blank=True)
    company_status = models.CharField(max_length=50, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    incorporated_on = models.DateField(null=True, blank=True)
    accounts_ref_day = models.PositiveSmallIntegerField(null=True, blank=True)
    accounts_ref_month = models.PositiveSmallIntegerField(null=True, blank=True)
    accounts_last_made_up = models.DateField(null=True, blank=True)
    accounts_category = models.CharField(max_length=50, blank=True)

    # From CH API enrichment only
    sic_codes = models.JSONField(default=list)

    # Enrichment tracking
    needs_enrichment = models.BooleanField(default=True)
    last_enriched_at = models.DateTimeField(null=True, blank=True)
    enrichment_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company_name", "company_number"]

    def __str__(self):
        return f"{self.company_number} - {self.company_name or 'Unknown'}"

    @property
    def year_end_display(self):
        if not self.accounts_ref_day or not self.accounts_ref_month:
            return ""
        month = calendar.month_abbr[self.accounts_ref_month]
        return f"{self.accounts_ref_day} {month}"


class Charge(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="charges",
    )
    charge_code = models.CharField(max_length=100, blank=True)
    holder_name = models.CharField(max_length=255, blank=True)
    created_on = models.DateField(null=True, blank=True)
    satisfied_on = models.DateField(null=True, blank=True)
    charge_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["-created_on", "charge_code"]

    def __str__(self):
        return f"{self.company_id} - {self.charge_code or 'charge'}"


class PSCEvent(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="psc_events",
    )
    psc_name = models.CharField(max_length=255, blank=True)
    psc_kind = models.CharField(max_length=100, blank=True)
    notified_on = models.DateField(null=True, blank=True)
    ceased_on = models.DateField(null=True, blank=True)
    nature_of_control = models.JSONField(default=list)

    class Meta:
        ordering = ["-notified_on", "psc_name"]

    def __str__(self):
        return f"{self.company_id} - {self.psc_name or 'psc'}"
