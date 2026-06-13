import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_django_cache_table"),
    ]

    operations = [
        migrations.AlterField(
            model_name="charge",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="charges",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="psc",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pscs",
                to="core.company",
            ),
        ),
    ]
