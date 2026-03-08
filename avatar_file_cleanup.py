"""
Avatar File Cleanup Script
This script cleans up inconsistent avatar files.
"""

import os
import re
from pathlib import Path
from PIL import Image

def cleanup_avatar_files():
    """Clean up avatar files with incorrect extensions."""

    media_dir = Path(__file__).parent / 'media' / 'avatars'

    print("=== Avatar File Cleanup ===\n")

    if not media_dir.exists():
        print("Avatar storage directory does not exist.")
        return

    avatar_files = list(media_dir.glob('*'))
    print(f"Found {len(avatar_files)} avatar files")

    pattern = r'user_(\d+)_([a-f0-9]{8})\.([a-z]+)'

    for file in avatar_files:
        match = re.match(pattern, file.name)
        if match:
            user_id = match.group(1)
            file_uuid = match.group(2)
            extension = match.group(3)

            if extension != 'jpg':
                print(f"\nProcessing file: {file.name}")
                print(f"  Extension: {extension} (should be 'jpg')")

                try:
                    # Try to open and verify the image
                    image = Image.open(file)

                    # Check if the image is valid
                    if image.format == 'JPEG':
                        print(f"  [+] Image is JPEG format")
                        new_name = f"user_{user_id}_{file_uuid}.jpg"
                        new_path = file.with_name(new_name)

                        # Rename the file
                        file.rename(new_path)
                        print(f"  [+] Renamed to: {new_name}")

                    else:
                        print(f"  [INFO] Image format: {image.format}")
                        print(f"  [+] Converting to JPEG format...")

                        # Convert to JPEG
                        new_name = f"user_{user_id}_{file_uuid}.jpg"
                        new_path = file.with_name(new_name)

                        # Convert image to JPEG
                        if image.mode in ('RGBA', 'LA'):
                            background = Image.new('RGB', image.size, (255, 255, 255))
                            background.paste(image, mask=image.split()[-1])
                            image = background
                        elif image.mode != 'RGB':
                            image = image.convert('RGB')

                        # Resize if needed
                        max_size = (400, 400)
                        image.thumbnail(max_size, Image.Resampling.LANCZOS)

                        # Save as JPEG
                        image.save(new_path, format='JPEG', quality=85)

                        # Remove original file
                        file.unlink()

                        print(f"  [+] Converted and saved as: {new_name}")

                except Exception as e:
                    print(f"  [ERROR] Failed to process file: {e}")

        else:
            print(f"\nFile '{file.name}' doesn't match expected pattern")

    print("\n=== Summary ===")
    print("Files with incorrect extensions have been renamed if they are JPEG format.")

def main():
    """Run cleanup."""
    cleanup_avatar_files()

if __name__ == "__main__":
    main()