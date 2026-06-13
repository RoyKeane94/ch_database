import calendar

from django.db import models


class Company(models.Model):
    company_number = models.CharField(max_length=8, primary_key=True)
    company_name = models.CharField(max_length=255, blank=True)
    company_status = models.CharField(max_length=50, blank=True)
    company_type = models.CharField(max_length=100, blank=True)
    jurisdiction = models.CharField(max_length=50, blank=True)
    date_of_creation = models.DateField(null=True, blank=True)
    sic_codes = models.JSONField(default=list)

    registered_premises = models.CharField(max_length=255, blank=True)
    registered_address_line_1 = models.CharField(max_length=255, blank=True)
    registered_address_line_2 = models.CharField(max_length=255, blank=True)
    registered_locality = models.CharField(max_length=100, blank=True)
    registered_region = models.CharField(max_length=100, blank=True)
    registered_postal_code = models.CharField(max_length=20, blank=True)
    registered_country = models.CharField(max_length=100, blank=True)
    registered_po_box = models.CharField(max_length=50, blank=True)
    registered_care_of = models.CharField(max_length=255, blank=True)

    accounts_next_due = models.DateField(null=True, blank=True)
    accounts_overdue = models.BooleanField(default=False)
    confirmation_next_due = models.DateField(null=True, blank=True)
    confirmation_overdue = models.BooleanField(default=False)
    has_insolvency_history = models.BooleanField(default=False)

    # CSV import fields (seed data before API enrichment)
    company_category = models.CharField(max_length=100, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    accounts_ref_day = models.PositiveSmallIntegerField(null=True, blank=True)
    accounts_ref_month = models.PositiveSmallIntegerField(null=True, blank=True)
    accounts_last_made_up = models.DateField(null=True, blank=True)
    accounts_category = models.CharField(max_length=50, blank=True)

    needs_enrichment = models.BooleanField(default=True)
    enrichment_error = models.TextField(blank=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company_name", "company_number"]
        indexes = [
            models.Index(fields=["needs_enrichment"], name="core_co_needs_enr_idx"),
            models.Index(
                fields=["needs_enrichment", "last_fetched_at"],
                name="core_co_enrich_stat_idx",
            ),
            models.Index(fields=["company_status"], name="core_co_status_idx"),
            models.Index(fields=["company_name"], name="core_co_name_idx"),
        ]

    def __str__(self):
        return f"{self.company_number} - {self.company_name or 'Unknown'}"

    @property
    def year_end_display(self):
        if not self.accounts_ref_day or not self.accounts_ref_month:
            return ""
        month = calendar.month_abbr[self.accounts_ref_month]
        return f"{self.accounts_ref_day} {month}"

    @property
    def registered_address_display(self):
        parts = [
            self.registered_premises,
            self.registered_address_line_1,
            self.registered_address_line_2,
            self.registered_locality,
            self.registered_region,
            self.registered_postal_code,
            self.registered_country,
        ]
        return ", ".join(part for part in parts if part)

    @property
    def companies_house_url(self):
        return (
            "https://find-and-update.company-information.service.gov.uk/company/"
            f"{self.company_number}"
        )


class PersonEntitled(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Charge(models.Model):
    charge_code = models.CharField(max_length=100, primary_key=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="charges",
    )
    charge_number = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=50, blank=True)
    persons_entitled = models.ManyToManyField(PersonEntitled, blank=True, related_name="charges")
    contains_fixed_charge = models.BooleanField(default=False)
    contains_floating_charge = models.BooleanField(default=False)
    floating_charge_covers_all = models.BooleanField(default=False)
    contains_negative_pledge = models.BooleanField(default=False)
    created_on = models.DateField(null=True, blank=True)
    delivered_on = models.DateField(null=True, blank=True)
    satisfied_on = models.DateField(null=True, blank=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on", "charge_code"]

    def __str__(self):
        return f"{self.company_id} - {self.charge_code}"


class PSC(models.Model):
    psc_id = models.CharField(max_length=255, primary_key=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="pscs",
    )
    kind = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=255, blank=True)
    ceased = models.BooleanField(default=False)
    notified_on = models.DateField(null=True, blank=True)
    ceased_on = models.DateField(null=True, blank=True)
    natures_of_control = models.JSONField(default=list)

    class Meta:
        ordering = ["-notified_on", "name"]
        verbose_name = "PSC"
        verbose_name_plural = "PSCs"

    def __str__(self):
        return f"{self.company_id} - {self.name or 'psc'}"
