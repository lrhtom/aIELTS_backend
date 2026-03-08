"""
Avatar Access Test Script
Tests whether avatar URLs are correctly accessible.
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
sys.path.append(str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.backend.settings')

try:
    django.setup()

    from backend.backend import settings
    print(f"DEBUG mode: {settings.DEBUG}")
    print(f"MEDIA_URL: {settings.MEDIA_URL}")
    print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")

    # Check avatar files
    media_dir = Path(settings.MEDIA_ROOT) / 'avatars'

    if media_dir.exists():
        avatar_files = list(media_dir.glob('*.jpg'))
        print(f"\nFound {len(avatar_files)} avatar files:")

        for file in avatar_files:
            relative_path = f"avatars/{file.name}"
            avatar_url = f"{settings.MEDIA_URL}{relative_path}"
            print(f"\n  File: {file.name}")
            print(f"  Avatar URL: {avatar_url}")
            print(f"  Expected frontend URL: http://localhost:5173{avatar_url}")

    # Check if Django media serving is configured
    from backend.backend import urls

    print("\n=== Django URL Configuration ===")
    print("In urls.py, media files are served when DEBUG=True:")
    print("  urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)")

except Exception as e:
    print(f"Error: {e}")
    print("\nManual URL check:")
    print("Avatar files are at: E:/code/web/work/aIELTS/backend/media/avatars/")
    print("Expected URLs: /media/avatars/user_{id}_{uuid}.jpg")
    print("Frontend should access: http://localhost:5173/media/avatars/user_{id}_{uuid}.jpg")

print("\n=== Debug Steps ===")
print("1. Check browser console for 404 errors")
print("2. Verify avatar_url returned by backend API")
print("3. Check if frontend can access avatar URLs")
print("4. Verify Django DEBUG=True for media file serving")