from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_psc_controller_company_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="Officer",
            fields=[
                ("officer_id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("officer_role", models.CharField(blank=True, max_length=100)),
                ("appointed_on", models.DateField(blank=True, null=True)),
                ("resigned_on", models.DateField(blank=True, null=True)),
                ("nationality", models.CharField(blank=True, max_length=100)),
                ("occupation", models.CharField(blank=True, max_length=255)),
                ("country_of_residence", models.CharField(blank=True, max_length=100)),
                ("date_of_birth_month", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("date_of_birth_year", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("person_number", models.CharField(blank=True, max_length=64)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="officers",
                        to="core.company",
                    ),
                ),
            ],
            options={
                "ordering": ["name", "officer_role"],
            },
        ),
        migrations.AddIndex(
            model_name="officer",
            index=models.Index(fields=["name"], name="core_off_name_idx"),
        ),
        migrations.AddIndex(
            model_name="officer",
            index=models.Index(fields=["officer_role", "resigned_on"], name="core_off_role_idx"),
        ),
        migrations.AddIndex(
            model_name="officer",
            index=models.Index(fields=["person_number"], name="core_off_person_idx"),
        ),
    ]
