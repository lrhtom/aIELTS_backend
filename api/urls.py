from django.urls import path
from . import reading_views
from . import listening_views
from . import speaking_views
from . import speaking_views
from . import writing_views
from . import prompt_views
from . import auth_views
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    # ---- 鉴权与用户 API ----
    path('auth/register', auth_views.UserRegistrationView.as_view(), name='auth_register'),
    path('auth/login', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile', auth_views.UserProfileView.as_view(), name='auth_profile'),

    # ---- 业务 API ----
    path('reading/generate', reading_views.generate_reading, name='generate_reading'),
    path('listening/generate', listening_views.generate_listening, name='generate_listening'),
    path('listening/audio', listening_views.generate_listening_audio, name='listening_audio'),
    path('speaking/chat', speaking_views.speaking_chat, name='speaking_chat'),
    path('speaking/transcribe', speaking_views.speaking_transcribe, name='speaking_transcribe'),
    path('writing/generate', writing_views.generate_writing, name='generate_writing'),
    path('prompts/', prompt_views.prompt_list, name='prompt_list'),
]
