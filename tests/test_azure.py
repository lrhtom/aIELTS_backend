import os
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk

load_dotenv()
speech_key = os.getenv("AZURE_SPEECH_KEY", "")
service_region = os.getenv("AZURE_SPEECH_REGION", "switzerlandnorth")

print(f"Key: {speech_key[:5]}... Region: {service_region}")

try:
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    print("Success config")
except Exception as e:
    print(f"Error: {e}")
