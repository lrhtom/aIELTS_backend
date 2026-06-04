import os
import sys
import django
import requests

sys.path.append('e:/code/web/work/aIELTS/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aIELTS.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
user = User.objects.first()
refresh = RefreshToken.for_user(user)
access_token = str(refresh.access_token)

try:
    res = requests.post(
        'http://127.0.0.1:8000/api/writing/synonyms', 
        json={'words': ['people', 'risk']},
        headers={'Authorization': f'Bearer {access_token}'}
    )
    print(res.status_code)
    print(res.text)
except Exception as e:
    print(e)
