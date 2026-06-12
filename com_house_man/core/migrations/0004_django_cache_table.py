from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable")


def drop_cache_table(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS django_cache")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_production_indexes"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
