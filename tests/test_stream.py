import os
import django
import sys
import json

sys.path.append(r'e:\code\web\work\aIELTS\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.test import RequestFactory
from api.practice.writing_task1_ai_teacher_views import generate_task1_ai_teacher_lesson
from api.models import User

# Get any user
user = User.objects.first()

factory = RequestFactory()
request = factory.post('/api/writing/task1-ai-teacher/generate', {
    'topic': 'The graph below shows the changes in food consumption by Chinese people between 1985 and 2010.'
}, content_type='application/json')
request.user = user

response = generate_task1_ai_teacher_lesson(request)

# Since it's a StreamingHttpResponse, we need to consume it
output = ""
for chunk in response.streaming_content:
    chunk_str = chunk.decode('utf-8')
    print("Received chunk:", chunk_str[:100], "...")
    output += chunk_str

with open(r'e:\code\web\work\aIELTS\scratch\test_stream_output.txt', 'w', encoding='utf-8') as f:
    f.write(output)
print("Done, output written to test_stream_output.txt")
