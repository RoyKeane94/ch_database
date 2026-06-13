from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from core.models import Charge, Company, PSC
from core.sync_stats import invalidate_sync_stats_cache

DEFAULT_BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Delete companies with dissolved or liquidation status."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many companies would be deleted without deleting.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Companies to delete per transaction (default: {DEFAULT_BATCH_SIZE}).",
        )

    def handle(self, *args, **options):
        queryset = Company.objects.filter(
            Q(company_status__icontains="dissolved")
            | Q(company_status__icontains="liquidation")
        )
        count = queryset.count()

        if count == 0:
            self.stdout.write("No dissolved or liquidation companies found.")
            return

        breakdown = (
            queryset.values("company_status")
            .annotate(count=Count("pk"))
            .order_by("company_status")
        )

        self.stdout.write(f"Matched {count} company record(s):")
        for row in breakdown:
            label = row["company_status"] or "(blank)"
            self.stdout.write(f"  {label}: {row['count']}")

        if options["dry_run"]:
            self.stdout.write("Dry run — no records deleted.")
            return

        batch_size = options["batch_size"]
        totals = defaultdict(int)
        deleted_companies = 0
        batch = []

        for company_number in queryset.values_list("company_number", flat=True).iterator(
            chunk_size=batch_size
        ):
            batch.append(company_number)
            if len(batch) < batch_size:
                continue

            deleted_companies += self._delete_batch(batch, totals)
            batch = []
            if deleted_companies % (batch_size * 10) == 0:
                self.stdout.write(f"Deleted {deleted_companies}/{count} companies...")

        if batch:
            deleted_companies += self._delete_batch(batch, totals)

        invalidate_sync_stats_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_companies} company record(s) "
                f"({sum(totals.values())} total rows including related charges and PSCs)."
            )
        )
        for model_label, model_count in sorted(totals.items()):
            self.stdout.write(f"  {model_label}: {model_count}")

    def _delete_batch(self, company_numbers, totals):
        with transaction.atomic():
            for model_label, model_count in PSC.objects.filter(
                company_id__in=company_numbers
            ).delete()[1].items():
                totals[model_label] += model_count

            for model_label, model_count in Charge.objects.filter(
                company_id__in=company_numbers
            ).delete()[1].items():
                totals[model_label] += model_count

            deleted, breakdown = Company.objects.filter(
                company_number__in=company_numbers
            ).delete()
            for model_label, model_count in breakdown.items():
                totals[model_label] += model_count

        return deleted
