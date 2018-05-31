# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2018-05-31 10:21
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('django_mailbox', '0007_auto_20180529_1124'),
    ]

    operations = [
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(default=None, max_length=254, null=True, unique=True)),
                ('name', models.CharField(max_length=128, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Folder',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
            ],
        ),
        migrations.CreateModel(
            name='Mail',
            fields=[
                ('message_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='django_mailbox.Message')),
                ('folder', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='api.Folder')),
            ],
            bases=('django_mailbox.message',),
        ),
        migrations.CreateModel(
            name='CustomMailbox',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
            },
            bases=('django_mailbox.mailbox',),
        ),
        migrations.AddField(
            model_name='folder',
            name='mailbox',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='folders', to='django_mailbox.Mailbox'),
        ),
        migrations.AddField(
            model_name='contact',
            name='folder',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='api.Folder'),
        ),
    ]
