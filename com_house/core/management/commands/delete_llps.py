from django.core.management.base import BaseCommand

from core.models import Company

LLP_CATEGORY = "Limited Liability Partnership"


class Command(BaseCommand):
    help = "Delete companies classified as Limited Liability Partnerships."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many companies would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        queryset = Company.objects.filter(company_category__iexact=LLP_CATEGORY)
        count = queryset.count()

        if count == 0:
            self.stdout.write("No Limited Liability Partnership companies found.")
            return

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} company record(s).")
            return

        deleted, breakdown = queryset.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} company record(s) "
                f"({deleted} total rows including related charges and PSC events)."
            )
        )
        for model_label, model_count in sorted(breakdown.items()):
            self.stdout.write(f"  {model_label}: {model_count}")
