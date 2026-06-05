import os
import requests
from dotenv import load_dotenv

load_dotenv()

base_url = os.environ.get('AI_BASE_URL').replace('/chat/completions', '/audio/speech')
api_key = os.environ.get('AI_API_KEY')

print(f"Testing TTS endpoint: {base_url}")

try:
    response = requests.post(
        base_url,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'tts-1',
            'input': 'Hello, testing TTS audio generation.',
            'voice': 'alloy'
        }
    )
    print(response.status_code)
    if response.status_code == 200:
        with open('test_audio.mp3', 'wb') as f:
            f.write(response.content)
        print("Success! Saved test_audio.mp3")
    else:
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
