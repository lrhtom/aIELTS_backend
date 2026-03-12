from django.urls import path
from . import reading_views
from . import listening_views
from . import speaking_views
from . import writing_views
from . import writing_chart_views
from . import writing_task2_views
from . import prompt_views
from . import auth_views
from . import balance_views
from . import feedback_views
from . import background_views
from . import admin_views
from .auth_views import SendVerificationCodeView, CustomLoginView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    # ---- 鉴权与用户 API ----
    path('auth/register', auth_views.UserRegistrationView.as_view(), name='auth_register'),
    path('auth/send-code', SendVerificationCodeView.as_view(), name='auth_send_code'),
    path('auth/login', CustomLoginView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile', auth_views.UserProfileView.as_view(), name='auth_profile'),
    path('auth/avatar', auth_views.AvatarUploadView.as_view(), name='avatar_upload'),
    path('auth/delete-account', auth_views.DeleteAccountView.as_view(), name='delete_account'),
    path('auth/background', background_views.BackgroundSettingsView.as_view(), name='user_background'),
    path('auth/background/image', background_views.BackgroundImageUploadView.as_view(), name='user_background_image'),

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
    path('writing/chart/generate', writing_chart_views.generate_chart, name='generate_chart'),
    path('writing/chart/evaluate', writing_chart_views.evaluate_chart, name='evaluate_chart'),
    path('writing/task2/generate', writing_task2_views.generate_task2, name='generate_task2'),
    path('writing/task2/evaluate', writing_task2_views.evaluate_task2, name='evaluate_task2'),
    path('prompts/', prompt_views.prompt_list, name='prompt_list'),
    path('prompts/<int:pk>/like/', prompt_views.prompt_like, name='prompt_like'),
    path('prompts/<int:pk>/favorite/', prompt_views.prompt_favorite, name='prompt_favorite'),
    path('feedback/submit', feedback_views.FeedbackCreateView.as_view(), name='feedback_submit'),

    # ---- 管理后台 API ----
    path('admin/feedback', admin_views.AdminFeedbackListView.as_view(), name='admin_feedback_list'),
    path('admin/feedback/<int:pk>', admin_views.AdminFeedbackUpdateView.as_view(), name='admin_feedback_update'),
    path('admin/feedback/<int:pk>/delete', admin_views.AdminFeedbackDeleteView.as_view(), name='admin_feedback_delete'),
    path('admin/users', admin_views.AdminUserListView.as_view(), name='admin_user_list'),
    path('admin/users/<int:pk>/ban', admin_views.AdminUserBanToggleView.as_view(), name='admin_user_ban_toggle'),
    path('admin/users/<int:pk>/delete', admin_views.AdminUserDeleteView.as_view(), name='admin_user_delete'),
]
