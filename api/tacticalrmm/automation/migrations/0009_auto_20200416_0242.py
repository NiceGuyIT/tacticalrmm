# Generated by Django 3.0.5 on 2020-04-16 02:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0008_automatedtask_execution_time'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automatedtask',
            name='run_time_minute',
            field=models.CharField(blank=True, max_length=5, null=True),
        ),
    ]
