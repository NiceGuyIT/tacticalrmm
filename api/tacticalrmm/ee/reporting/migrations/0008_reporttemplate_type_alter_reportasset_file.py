# Generated by Django 4.1.3 on 2022-12-16 04:09

from django.db import migrations, models
import ee.reporting.storage


class Migration(migrations.Migration):
    dependencies = [
        ("reporting", "0007_remove_reportdataquery_yaml_query_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="reporttemplate",
            name="type",
            field=models.CharField(
                choices=[("markdown", "Markdown"), ("html", "Html")],
                default="markdown",
                max_length=15,
            ),
        )
    ]
