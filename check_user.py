import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.filter(username='lrhtom').first()

if not user:
    print("User 'lrhtom' does NOT exist.")
else:
    print("User 'lrhtom' exists.")
    print("Active:", user.is_active)
    if hasattr(user, 'is_banned'):
        print("Banned:", getattr(user, 'is_banned', False))
    print("Has password set:", bool(user.password))
    # We can't decrypt the password, but we can reset it if the user wants.
    print("Note: We cannot read the original password because it is hashed.")
