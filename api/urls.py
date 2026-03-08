from django.urls import path
from . import reading_views
from . import listening_views
from . import speaking_views
from . import writing_views
from . import prompt_views
from . import auth_views
from . import balance_views
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
    path('auth/avatar', auth_views.AvatarUploadView.as_view(), name='avatar_upload'),
    path('auth/delete-account', auth_views.DeleteAccountView.as_view(), name='delete_account'),

    # ---- AT币管理 API ----
    path('balance', balance_views.get_balance, name='get_balance'),
    path('balance/check', balance_views.check_balance, name='check_balance'),
    path('balance/consume', balance_views.consume_at, name='consume_at'),
    path('balance/add', balance_views.add_at, name='add_at'),

    # ---- 业务 API ----
    path('reading/generate', reading_views.generate_reading, name='generate_reading'),
    path('listening/generate', listening_views.generate_listening, name='generate_listening'),
    path('listening/audio', listening_views.generate_listening_audio, name='listening_audio'),
    path('speaking/chat', speaking_views.speaking_chat, name='speaking_chat'),
    path('speaking/transcribe', speaking_views.speaking_transcribe, name='speaking_transcribe'),
    path('writing/generate', writing_views.generate_writing, name='generate_writing'),
    path('prompts/', prompt_views.prompt_list, name='prompt_list'),
]
