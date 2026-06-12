from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonEntitled",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.RenameField(
            model_name="company",
            old_name="incorporated_on",
            new_name="date_of_creation",
        ),
        migrations.RenameField(
            model_name="company",
            old_name="last_enriched_at",
            new_name="last_fetched_at",
        ),
        migrations.AddField(
            model_name="company",
            name="accounts_next_due",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="accounts_overdue",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="company",
            name="company_type",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="company",
            name="confirmation_next_due",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="confirmation_overdue",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="company",
            name="has_insolvency_history",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="company",
            name="jurisdiction",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_address_line_1",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_address_line_2",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_care_of",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_country",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_locality",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_po_box",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_postal_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_premises",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="company",
            name="registered_region",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.DeleteModel(
            name="Charge",
        ),
        migrations.DeleteModel(
            name="PSCEvent",
        ),
        migrations.CreateModel(
            name="Charge",
            fields=[
                ("charge_code", models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("charge_number", models.PositiveIntegerField(blank=True, null=True)),
                ("status", models.CharField(blank=True, max_length=50)),
                ("contains_fixed_charge", models.BooleanField(default=False)),
                ("contains_floating_charge", models.BooleanField(default=False)),
                ("floating_charge_covers_all", models.BooleanField(default=False)),
                ("contains_negative_pledge", models.BooleanField(default=False)),
                ("created_on", models.DateField(blank=True, null=True)),
                ("delivered_on", models.DateField(blank=True, null=True)),
                ("satisfied_on", models.DateField(blank=True, null=True)),
                ("last_fetched_at", models.DateTimeField(blank=True, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="charges",
                        to="core.company",
                    ),
                ),
                (
                    "persons_entitled",
                    models.ManyToManyField(blank=True, related_name="charges", to="core.personentitled"),
                ),
            ],
            options={
                "ordering": ["-created_on", "charge_code"],
            },
        ),
        migrations.CreateModel(
            name="PSC",
            fields=[
                ("psc_id", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("kind", models.CharField(blank=True, max_length=100)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("ceased", models.BooleanField(default=False)),
                ("notified_on", models.DateField(blank=True, null=True)),
                ("ceased_on", models.DateField(blank=True, null=True)),
                ("natures_of_control", models.JSONField(default=list)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pscs",
                        to="core.company",
                    ),
                ),
            ],
            options={
                "verbose_name": "PSC",
                "verbose_name_plural": "PSCs",
                "ordering": ["-notified_on", "name"],
            },
        ),
    ]
