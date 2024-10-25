# Generated by Django 2.0.7 on 2018-09-10 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_update_dates'),
    ]

    operations = [
        migrations.CreateModel(
            name='Template',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner', models.IntegerField(default=None, null=True, verbose_name='Owner')),
                ('alias', models.CharField(max_length=128, unique=True, verbose_name='Alias')),
                ('name', models.CharField(max_length=128, verbose_name='Name')),
                ('subject', models.CharField(max_length=128, verbose_name='Subject')),
                ('body', models.TextField(blank=True, default='', verbose_name='Body')),
            ],
        ),
    ]
