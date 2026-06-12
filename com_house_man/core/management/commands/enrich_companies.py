from django.core.management.base import BaseCommand
from django.utils import timezone

from core.ch_client import MIN_REQUEST_INTERVAL, CompaniesHouseClient
from core.enrichment import enrich_company, format_enrichment_error
from core.models import Company
from core.sync_stats import invalidate_sync_stats_cache

DEFAULT_BATCH_SIZE = 180


class Command(BaseCommand):
    help = (
        "Fetch Companies House profile, charges, and PSC data for pending companies. "
        "Makes three API calls per company with built-in rate limiting."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Maximum companies to process in one run (default: {DEFAULT_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--min-interval",
            type=float,
            default=MIN_REQUEST_INTERVAL,
            help=(
                "Minimum seconds between API requests "
                f"(default: {MIN_REQUEST_INTERVAL}, ~545 requests per 5 minutes)."
            ),
        )
        parser.add_argument(
            "--company-number",
            type=str,
            help="Enrich a single company number instead of the pending queue.",
        )

    def handle(self, *args, **options):
        client = CompaniesHouseClient(min_interval=options["min_interval"])
        batch_size = options["batch_size"]
        company_number = (options.get("company_number") or "").strip()

        if company_number:
            companies = Company.objects.filter(company_number=company_number.zfill(8))
            if not companies.exists():
                self.stderr.write(f"Company not found: {company_number}")
                return
        else:
            companies = Company.objects.filter(needs_enrichment=True).order_by(
                "created_at"
            )[:batch_size]
            if not companies:
                self.stdout.write("No companies queued for enrichment.")
                return

        success_count = 0
        failure_count = 0

        for company in companies:
            try:
                enrich_company(client, company)
                success_count += 1
                self.stdout.write(f"Fetched {company.company_number}")
            except Exception as exc:  # noqa: BLE001
                failure_count += 1
                company.enrichment_error = format_enrichment_error(exc)
                company.needs_enrichment = False
                company.last_fetched_at = None
                company.save(
                    update_fields=["enrichment_error", "needs_enrichment", "last_fetched_at"]
                )
                self.stderr.write(
                    f"Failed {company.company_number}: {company.enrichment_error}"
                )

        if success_count or failure_count:
            invalidate_sync_stats_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetch run complete at {timezone.now()}: "
                f"succeeded={success_count}, failed={failure_count}"
            )
        )
