# Generated by Django 2.0.7 on 2018-08-06 16:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_auto_20180730_1008'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mail',
            name='body',
            field=models.TextField(blank=True, default='', verbose_name='Body'),
        ),
    ]