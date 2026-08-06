from django.core.management.base import BaseCommand

from core.models import Company, PSC

CORPORATE = "corporate-entity-person-with-significant-control"
BATCH = 1000


class Command(BaseCommand):
    help = (
        "Backfill PSC.controller_company_number by matching corporate PSC names "
        "to companies already in the register."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many rows would be updated without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        qs = PSC.objects.filter(
            kind=CORPORATE,
            controller_company_number="",
        ).exclude(name="")

        # Build lowercase name -> company_number map for companies in register.
        name_map = {}
        for number, name in Company.objects.exclude(company_name="").values_list(
            "company_number", "company_name"
        ):
            key = name.casefold()
            name_map.setdefault(key, number)

        updated = 0
        batch = []
        for psc in qs.iterator(chunk_size=BATCH):
            number = name_map.get((psc.name or "").casefold())
            if not number:
                continue
            psc.controller_company_number = number
            batch.append(psc)
            if len(batch) >= BATCH:
                updated += self._flush(batch, dry_run)
                batch = []
        updated += self._flush(batch, dry_run)

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} corporate PSC links."))

    def _flush(self, batch, dry_run):
        if not batch:
            return 0
        if dry_run:
            return len(batch)
        PSC.objects.bulk_update(batch, ["controller_company_number"])
        return len(batch)
