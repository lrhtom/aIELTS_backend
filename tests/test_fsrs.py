import os
import sys
import django
from datetime import datetime, timezone

sys.path.append('e:/code/web/work/aIELTS/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aIELTS.settings')
django.setup()

from api.core.fsrs_utils import fsrs_schedule

card = {
    'state': 2,
    'stability': 2.0,
    'difficulty': 5.0,
    'reps': 1,
    'lapses': 0,
    'last_review': datetime.now(timezone.utc).isoformat()
}

try:
    res = fsrs_schedule(card, 1, datetime.now(timezone.utc))
    print("SUCCESS:", res)
except Exception as e:
    print("ERROR:", e)
