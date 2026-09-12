from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Run VACUUM ANALYZE on core tables to reclaim dead tuple space."

    def handle(self, *args, **options):
        tables = (
            "core_company",
            "core_charge",
            "core_psc",
            "core_officer",
            "core_personentitled",
            "core_charge_persons_entitled",
        )
        with connection.cursor() as cursor:
            for table in tables:
                self.stdout.write(f"Vacuuming {table}…")
                cursor.execute(f"VACUUM ANALYZE {table}")
        self.stdout.write(self.style.SUCCESS("VACUUM ANALYZE complete."))
