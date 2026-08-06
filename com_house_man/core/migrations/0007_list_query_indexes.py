from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_sic_codes_gin_index"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["accounts_category"], name="core_co_accts_cat_idx"),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["-created_at"], name="core_co_created_idx"),
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["-date_of_creation"], name="core_co_date_crea_idx"),
        ),
        migrations.AddIndex(
            model_name="charge",
            index=models.Index(fields=["company", "satisfied_on"], name="core_ch_co_sat_idx"),
        ),
        migrations.AddIndex(
            model_name="charge",
            index=models.Index(fields=["status"], name="core_ch_status_idx"),
        ),
    ]
