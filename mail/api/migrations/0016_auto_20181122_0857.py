# Generated by Django 2.0.7 on 2018-11-22 08:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_auto_20181025_1953'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mailbox',
            name='from_email',
            field=models.CharField(blank=True, default=None, help_text="Example: MailBot &lt;mailbot@yourdomain.com&gt;<br />'From' header to set for outgoing email.<br /><br />If you do not use this e-mail inbox for outgoing mail, this setting is unnecessary.<br />If you send e-mail without setting this, your 'From' header will'be set to match the setting `DEFAULT_FROM_EMAIL`.", max_length=255, null=True, unique=True, verbose_name='From email'),
        ),
    ]
