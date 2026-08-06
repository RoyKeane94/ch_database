from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_list_query_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="psc",
            name="controller_company_number",
            field=models.CharField(blank=True, db_index=True, max_length=8),
        ),
        migrations.AddIndex(
            model_name="psc",
            index=models.Index(fields=["name"], name="core_psc_name_idx"),
        ),
        migrations.AddIndex(
            model_name="psc",
            index=models.Index(
                fields=["kind", "ceased", "controller_company_number"],
                name="core_psc_ctrl_idx",
            ),
        ),
    ]
