from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_api_schema"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["needs_enrichment"], name="core_co_needs_enr_idx"),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(
                fields=["needs_enrichment", "last_fetched_at"],
                name="core_co_enrich_stat_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["company_status"], name="core_co_status_idx"),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["company_name"], name="core_co_name_idx"),
        ),
    ]
