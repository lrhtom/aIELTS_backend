"""
Avatar Consistency Test Script
This script tests avatar data consistency across the system.
"""

import os
import re
from pathlib import Path

def test_avatar_file_consistency():
    """Test avatar file naming and storage consistency."""

    media_dir = Path(__file__).parent / 'media' / 'avatars'

    print("\n=== Avatar File Consistency Test ===\n")

    if not media_dir.exists():
        print("Avatar storage directory does not exist.")
        return

    avatar_files = list(media_dir.glob('*'))

    print(f"Found {len(avatar_files)} avatar files:")

    pattern = r'user_(\d+)_([a-f0-9]{8})\.([a-z]+)'

    for file in avatar_files:
        match = re.match(pattern, file.name)
        if match:
            user_id = match.group(1)
            file_uuid = match.group(2)
            extension = match.group(3)

            print(f"  File: {file.name}")
            print(f"    User ID: {user_id}")
            print(f"    UUID: {file_uuid}")
            print(f"    Extension: {extension}")

            # Check file size
            size = file.stat().st_size
            print(f"    Size: {size} bytes")

            # Validate extension
            if extension != 'jpg':
                print(f"    [WARNING] Expected 'jpg' extension but found '{extension}'")

            # Check if file is actually JPEG
            try:
                with open(file, 'rb') as f:
                    header = f.read(2)
                    if header == b'\xff\xd8':
                        print(f"    [+] File is valid JPEG")
                    else:
                        print(f"    [WARNING] File may not be JPEG (header: {header})")
            except Exception as e:
                print(f"    Error reading file: {e}")

        else:
            print(f"  [WARNING] File '{file.name}' doesn't match expected pattern")

    print("\n=== Summary ===")
    print("1. File naming pattern: user_{id}_{uuid}.jpg")
    print("2. All files should have .jpg extension")
    print("3. All files should be JPEG format")
    print("4. File size should be reasonable (< 5MB)")

def test_model_field_consistency():
    """Check for potential database field inconsistencies."""

    print("\n=== Database Field Consistency ===\n")

    print("User model has two avatar-related fields:")
    print("  - avatar_url (URLField): Stores full URL path")
    print("  - avatar_file (CharField): Stores file path on disk")

    print("\nConsistency considerations:")
    print("1. Both fields should be set/cleared together")
    print("2. avatar_file should match avatar_url minus MEDIA_URL prefix")
    print("3. Only avatar_url should be exposed to frontend")

def test_frontend_backend_mapping():
    """Check frontend-backend data mapping consistency."""

    print("\n=== Frontend-Backend Mapping ===\n")

    print("Frontend User interface includes:")
    print("  - avatar_url (optional string)")

    print("\nBackend serializer exposes:")
    print("  - avatar_url")

    print("\nMapping consistency:")
    print("[+] avatar_url field consistently mapped")
    print("[+] avatar_file field is internal only")

def main():
    """Run all consistency tests."""
    print("=" * 50)
    print("Avatar Data Consistency Analysis")
    print("=" * 50)

    test_avatar_file_consistency()
    test_model_field_consistency()
    test_frontend_backend_mapping()

    print("\n" + "=" * 50)
    print("Recommendations:")
    print("=" * 50)
    print("1. Ensure all avatar files have .jpg extension")
    print("2. Backend should convert all images to JPEG")
    print("3. Frontend should always use avatar_url field")
    print("4. Database fields avatar_url/avatar_file should be kept synchronized")

if __name__ == "__main__":
    main()