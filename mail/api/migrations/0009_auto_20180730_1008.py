# Generated by Django 2.0.7 on 2018-07-30 10:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_auto_20180730_0849'),
    ]

    operations = [
        migrations.AlterField(
            model_name='folder',
            name='chains',
            field=models.ManyToManyField(related_name='folders', to='api.Chain'),
        ),
    ]
