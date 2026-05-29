lines = open('e:/code/web/work/aIELTS/backend/api/practice/listening_views.py', 'rb').readlines()
lines[265] = b'async def generate_listening_audio(request):\r\n'
lines[266] = b'    """POST /api/listening/audio"""\r\n'
open('e:/code/web/work/aIELTS/backend/api/practice/listening_views.py', 'wb').writelines(lines)
