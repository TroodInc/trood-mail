# Generated by Django 2.0.7 on 2018-07-30 08:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_custommailbox_shared'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mail',
            name='folder',
        ),
    ]