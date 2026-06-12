import csv
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.csv_utils import ensure_required_columns, parse_company_row
from core.models import Company

CHUNK_SIZE = 5_000


class Command(BaseCommand):
    help = "Import large company CSV files in chunks."

    def add_arguments(self, parser):
        parser.add_argument("path", type=str, help="Path to CSV file")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists() or not path.is_file():
            raise CommandError(f"File not found: {path}")

        start_time = time.time()
        existing_numbers = set(Company.objects.values_list("company_number", flat=True))
        seen_numbers = set()
        buffer = []
        processed = 0
        created = 0
        skipped = 0

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
                reader = csv.DictReader(file_obj)
                ensure_required_columns(reader.fieldnames)

                for row in reader:
                    processed += 1
                    company = parse_company_row(row)
                    if company is None:
                        skipped += 1
                        continue

                    number = company.company_number
                    if number in existing_numbers or number in seen_numbers:
                        skipped += 1
                        continue

                    seen_numbers.add(number)
                    buffer.append(company)

                    if len(buffer) >= CHUNK_SIZE:
                        Company.objects.bulk_create(buffer, ignore_conflicts=True)
                        created += len(buffer)
                        buffer.clear()
                        self._print_progress(processed, created, skipped, start_time)

                if buffer:
                    Company.objects.bulk_create(buffer, ignore_conflicts=True)
                    created += len(buffer)
                    self._print_progress(processed, created, skipped, start_time)
        except UnicodeDecodeError as exc:
            raise CommandError("Unable to decode CSV. Use UTF-8 encoding.") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: processed={processed}, created={created}, "
                f"skipped={skipped}, elapsed={elapsed:.2f}s"
            )
        )

    def _print_progress(self, processed, created, skipped, start_time):
        elapsed = time.time() - start_time
        self.stdout.write(
            f"Progress: processed={processed}, created={created}, "
            f"skipped={skipped}, elapsed={elapsed:.2f}s"
        )
