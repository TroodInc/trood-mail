# Generated by Django 2.0.7 on 2018-07-27 15:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_remove_folder_mailbox'),
    ]

    operations = [
        migrations.AddField(
            model_name='custommailbox',
            name='shared',
            field=models.BooleanField(default=False),
        ),
    ]
