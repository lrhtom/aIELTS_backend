"""Media key normalisation.

Two related changes:

1. Turn `User.avatar_url` and `User.bg_image_url` from URLField into
   CharField. They now hold a relative media key (e.g. `avatars/user_1_ab.jpg`)
   composed with `VITE_MEDIA_BASE` on the frontend. URLField would reject
   the relative form at validation time.

   `bg_image_url` stays polymorphic — external image URLs pasted by the user
   also live in this column — so we keep the max_length wide.

2. Data heal: strip the historical origin prefixes from existing rows so
   avatars uploaded before this migration stop pointing at `127.0.0.1`.
   Idempotent — safe to run twice.
"""
from django.db import migrations, models


LEGACY_PREFIXES = (
    'http://127.0.0.1:8000/media/',
    'http://47.85.195.208:8000/media/',
    'https://47.85.195.208:8000/media/',
    '/media/',
)


def strip_prefixes(value: str | None) -> str | None:
    if not value:
        return value
    for prefix in LEGACY_PREFIXES:
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def heal_rows(apps, schema_editor):
    User = apps.get_model('api', 'User')
    to_update = []
    for u in User.objects.only('id', 'avatar_url', 'bg_image_url').iterator():
        new_avatar = strip_prefixes(u.avatar_url)
        new_bg = strip_prefixes(u.bg_image_url)
        if new_avatar != u.avatar_url or new_bg != u.bg_image_url:
            u.avatar_url = new_avatar
            u.bg_image_url = new_bg
            to_update.append(u)
    if to_update:
        User.objects.bulk_update(to_update, ['avatar_url', 'bg_image_url'], batch_size=200)


def reverse_noop(apps, schema_editor):
    # No way to reliably reconstruct the original host prefix; leaving rows
    # in the healed state is safer than guessing.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0044_aiquestion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='avatar_url',
            field=models.CharField(max_length=500, blank=True, null=True, verbose_name='头像URL'),
        ),
        migrations.AlterField(
            model_name='user',
            name='bg_image_url',
            field=models.CharField(max_length=1000, blank=True, null=True, verbose_name='背景图片URL'),
        ),
        migrations.RunPython(heal_rows, reverse_noop),
    ]
