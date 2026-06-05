"""
Simple Avatar URL Test
"""

from pathlib import Path

def main():
    print("=== Avatar URL Test ===\n")

    # Check avatar files
    media_dir = Path(__file__).parent / 'media' / 'avatars'

    if not media_dir.exists():
        print("Avatar storage directory does not exist.")
        return

    avatar_files = list(media_dir.glob('*.jpg'))
    print(f"Found {len(avatar_files)} avatar files")

    for file in avatar_files:
        print(f"\nFile: {file.name}")
        print(f"Relative path: avatars/{file.name}")

        # MEDIA_URL is '/media/' in settings.py
        avatar_url = f"/media/avatars/{file.name}"
        print(f"Expected avatar_url: {avatar_url}")

        print(f"File exists: {file.exists()}")
        print(f"File size: {file.stat().st_size} bytes")

    print("\n=== Summary ===")
    print("Avatar URLs should be like: /media/avatars/user_1_7738ca4b.jpg")
    print("Frontend should be able to access these URLs.")
    print("If DEBUG=True, Django serves files from MEDIA_ROOT.")

if __name__ == "__main__":
    main()