import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.filter(username='lrhtom').first()

if user:
    user.set_password('lrhtom123456')
    user.save()
    print("Password for 'lrhtom' has been reset to 'lrhtom123456'")
else:
    print("User not found.")
