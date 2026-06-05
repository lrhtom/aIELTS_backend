"""
Avatar URL Test Script
This script tests avatar URL generation and access.
"""

import os
from pathlib import Path

def test_avatar_url_generation():
    """Test avatar URL generation logic."""

    print("\n=== Avatar URL Generation Test ===\n")

    # Check settings.py MEDIA_URL
    from backend.backend import settings
    print(f"MEDIA_URL in settings: {settings.MEDIA_URL}")
    print(f"MEDIA_ROOT in settings: {settings.MEDIA_ROOT}")
    print(f"DEBUG mode: {settings.DEBUG}")

    # Check avatar files
    media_dir = Path(__file__).parent / 'media' / 'avatars'

    if not media_dir.exists():
        print("\nAvatar storage directory does not exist.")
        return

    avatar_files = list(media_dir.glob('*.jpg'))
    print(f"\nFound {len(avatar_files)} avatar files")

    for file in avatar_files:
        relative_path = f"avatars/{file.name}"
        print(f"\nFile: {file.name}")
        print(f"Relative path: {relative_path}")

        # Calculate URL based on logic in auth_views.py
        avatar_url = f"{settings.MEDIA_URL}{relative_path}"
        print(f"Generated avatar_url: {avatar_url}")

        # Check if file exists
        print(f"File exists: {file.exists()}")
        print(f"File size: {file.stat().st_size} bytes")

    print("\n=== Expected URLs ===\n")
    print("Based on MEDIA_URL='/media/', avatar URLs should be:")
    for file in avatar_files:
        expected_url = f"/media/avatars/{file.name}"
        print(f"  {expected_url}")

    print("\n=== Frontend Access Test ===\n")
    print("Frontend should access these URLs directly.")
    print("If DEBUG=True, Django serves files via:")
    print("  urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)")

def test_url_patterns():
    """Check URL routing for media files."""

    print("\n=== URL Routing Test ===\n")

    try:
        # Check urls.py configuration
        print("In urls.py:")
        print("  if settings.DEBUG:")
        print("    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)")

        print("\nThis means media files are served at:")
        print(f"  {settings.MEDIA_URL} -> maps to {settings.MEDIA_ROOT}")
    except Exception as e:
        print(f"Error checking URL patterns: {e}")

def main():
    """Run all tests."""
    print("=" * 50)
    print("Avatar URL Access Test")
    print("=" * 50)

    test_avatar_url_generation()
    test_url_patterns()

    print("\n" + "=" * 50)
    print("Diagnostic Steps:")
    print("=" * 50)
    print("1. Check if avatar_url returned by backend is correct")
    print("2. Check if frontend can access /media/avatars/ files")
    print("3. Verify DEBUG=True in Django settings")
    print("4. Check browser console for 404 errors")

if __name__ == "__main__":
    main()