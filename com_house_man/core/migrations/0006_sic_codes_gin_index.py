from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_cascade_foreign_keys"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS core_co_sic_codes_gin "
                "ON core_company USING gin (sic_codes jsonb_path_ops);"
            ),
            reverse_sql="DROP INDEX IF EXISTS core_co_sic_codes_gin;",
        ),
    ]
