from django.db import migrations


def create_sic_codes_gin(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS core_co_sic_codes_gin "
        "ON core_company USING gin (sic_codes jsonb_path_ops);"
    )


def drop_sic_codes_gin(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS core_co_sic_codes_gin;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_cascade_foreign_keys"),
    ]

    operations = [
        migrations.RunPython(create_sic_codes_gin, drop_sic_codes_gin),
    ]
