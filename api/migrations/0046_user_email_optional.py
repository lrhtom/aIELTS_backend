"""Allow User.email to be blank / null.

Registration no longer requires an email address. Existing rows already have
non-null values, so the field just relaxes its constraints — no data migration
needed.
"""
from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0045_media_key_normalization'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(
                _('email address'),
                blank=True,
                null=True,
                unique=True,
                max_length=254,
                error_messages={'unique': _("A user with that email already exists.")},
            ),
        ),
    ]
