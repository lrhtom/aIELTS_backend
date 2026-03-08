"""
Avatar Process Test
Tests avatar processing and URL generation logic.
"""

import uuid

def simulate_avatar_url_generation(user_id=1):
    """Simulate avatar URL generation logic from auth_views.py."""

    file_uuid = uuid.uuid4().hex[:8]

    # Logic from auth_views.py
    filename = f'avatars/user_{user_id}_{file_uuid}.jpg'
    relative_path = f'avatars/user_{user_id}_{file_uuid}.jpg'

    print(f"Generated filename: {filename}")
    print(f"Generated relative_path: {relative_path}")

    # MEDIA_URL is '/media/' in settings.py
    MEDIA_URL = '/media/'
    avatar_url = f"{MEDIA_URL}{relative_path}"

    print(f"Generated avatar_url: {avatar_url}")

    # Check expected URL format
    expected_pattern = f"/media/avatars/user_{user_id}_{file_uuid}.jpg"
    print(f"Expected pattern: {expected_pattern}")

    return avatar_url

def main():
    print("=== Avatar URL Generation Simulation ===\n")

    # Test multiple user IDs
    for user_id in [1, 2]:
        print(f"\nTesting user ID {user_id}:")
        avatar_url = simulate_avatar_url_generation(user_id)

        # Validate format
        if avatar_url.startswith('/media/') and avatar_url.endswith('.jpg'):
            print(f"[+] URL format is correct")
        else:
            print(f"[!] URL format is incorrect")

    print("\n=== Actual File URLs ===\n")

    # List actual files and their URLs
    files = [
        "user_1_33bc7b55.jpg",
        "user_1_7738ca4b.jpg",
        "user_2_30e10e3c.jpg",
        "user_2_3458b23e.jpg",
        "user_2_beac8dd5.jpg",
        "user_2_e788dd59.jpg"
    ]

    for file in files:
        avatar_url = f"/media/avatars/{file}"
        print(f"File: {file}")
        print(f"URL: {avatar_url}")
        print(f"Frontend access: http://localhost:5173{avatar_url}")

    print("\n=== Summary ===\n")
    print("Avatar URLs should be: /media/avatars/user_{id}_{uuid}.jpg")
    print("Frontend accesses them via: http://localhost:5173/media/avatars/user_{id}_{uuid}.jpg")
    print("Django serves files when DEBUG=True")

if __name__ == "__main__":
    main()