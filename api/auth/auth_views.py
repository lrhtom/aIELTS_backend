from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model
from api.serializers import UserRegistrationSerializer, UserSerializer
from api.core.email_service import send_verification_code, verify_code
from api.core.authentication import (
    ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME,
)
from datetime import timedelta
import os
import mimetypes
import secrets
from PIL import Image
import io
import uuid
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

User = get_user_model()


# Cookie lifetimes — keep in sync with simple-jwt's ACCESS_TOKEN_LIFETIME / REFRESH_TOKEN_LIFETIME.
ACCESS_COOKIE_MAX_AGE = 60 * 60          # 1 hour
REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _cookie_kwargs(httponly: bool, max_age: int) -> dict:
    """
    SameSite policy:
      - dev (DEBUG=True, plain HTTP)   → Lax + non-secure. Lax allows the cookie on
        same-site top-level navigations and the browser still sends it on XHR/fetch
        within the same registrable domain (localhost:5173 ↔ localhost:8000 count
        as same-site).
      - prod (HTTPS)                    → Lax + Secure. Strict would block links
        from external sites that should remain authenticated; Lax is the usual
        sweet spot.
    """
    is_secure = not settings.DEBUG
    return {
        'httponly': httponly,
        'secure': is_secure,
        'samesite': 'Lax',
        'max_age': max_age,
        'path': '/',
    }


def set_auth_cookies(response, *, access: str, refresh: str | None = None) -> None:
    """Attach access/refresh/csrf cookies to ``response``.

    Pass ``refresh=None`` for token-refresh responses where the refresh token
    didn't rotate (default SIMPLE_JWT setting). The CSRF token is rotated on
    every call so a stolen csrf cookie can't be replayed indefinitely.
    """
    response.set_cookie(ACCESS_COOKIE_NAME, access, **_cookie_kwargs(httponly=True, max_age=ACCESS_COOKIE_MAX_AGE))
    if refresh is not None:
        response.set_cookie(REFRESH_COOKIE_NAME, refresh, **_cookie_kwargs(httponly=True, max_age=REFRESH_COOKIE_MAX_AGE))
    response.set_cookie(
        CSRF_COOKIE_NAME, secrets.token_urlsafe(32),
        **_cookie_kwargs(httponly=False, max_age=REFRESH_COOKIE_MAX_AGE),
    )


def clear_auth_cookies(response) -> None:
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(name, path='/')

class CustomLoginView(APIView):
    """
    自定义登录视图：先验证凭据，再检查封号状态，最后签发 JWT。
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate
        username = request.data.get('username', '')
        password = request.data.get('password', '')

        print(f"[Login] Attempt for user: {username}")
        user = authenticate(request, username=username, password=password)
        
        if user is None:
            print(f"[Login] Failed: Invalid credentials for {username}")
            return Response({'error': 'INVALID_CREDENTIALS'}, status=status.HTTP_401_UNAUTHORIZED)
        
        print(f"[Login] Success: User {username} authenticated")

        if user.is_banned:
            return Response({'error': 'ACCOUNT_BANNED'}, status=status.HTTP_403_FORBIDDEN)

        # 刷新 Token ID 以实现单设备登录限制
        user.jwt_token_id = str(uuid.uuid4())
        # 自定义登录流程需手动维护最近登录时间
        user.last_login = timezone.now()
        user.save(update_fields=['jwt_token_id', 'last_login'])

        refresh = RefreshToken.for_user(user)
        # 将 Token ID 注入到 JWT 负载中
        refresh['jwt_token_id'] = user.jwt_token_id
        access_str = str(refresh.access_token)
        refresh_str = str(refresh)

        # Tokens are returned in the JSON body for backwards compatibility (older
        # clients still read them), but the canonical channel is now httpOnly cookies.
        response = Response({'access': access_str, 'refresh': refresh_str})
        set_auth_cookies(response, access=access_str, refresh=refresh_str)
        return response

class SendVerificationCodeView(APIView):
    """
    发邮箱验证码
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        username = request.data.get('username', '').strip()

        if not email or not username:
            return Response({'error': 'EMAIL_AND_USERNAME_REQUIRED'}, status=status.HTTP_400_BAD_REQUEST)

        # 检查邮箱或用户名是否已被注册
        if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
            return Response({'error': 'REGISTER_TAKEN'}, status=status.HTTP_400_BAD_REQUEST)

        success, message = send_verification_code(email, username)
        if success:
            return Response({'message': 'CODE_SENT'}, status=status.HTTP_200_OK)
        else:
            print(f"[Auth] Failed to send verification code to {email}: {message}")
            
            # 如果是配置限制类错误，返回 400 提示用户检查配置
            if "EMAIL_SERVICE_RESTRICTION" in message:
                return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({'error': message}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserRegistrationView(APIView):
    """
    处理用户注册请求的视图，注册前必须通过邮箱验证码。
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        code = request.data.get('verification_code', '').strip()

        # Verification code is only required when an email address is provided.
        # Users can register with just username + password.
        if email:
            if not code:
                return Response({'error': 'VERIFICATION_CODE_REQUIRED'}, status=status.HTTP_400_BAD_REQUEST)
            if not verify_code(email, code):
                return Response({'error': 'INVALID_CODE'}, status=status.HTTP_400_BAD_REQUEST)

        # 验证码通过后执行注册
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # 邮箱提供且验证码校验通过 → 邮箱已验证;否则 False
            user.is_email_verified = bool(email)
            user.jwt_token_id = str(uuid.uuid4())
            user.save(update_fields=['is_email_verified', 'jwt_token_id'])

            # 注册成功直接签发 Token，自动登录
            refresh = RefreshToken.for_user(user)
            refresh['jwt_token_id'] = user.jwt_token_id
            access_str = str(refresh.access_token)
            refresh_str = str(refresh)

            response = Response({
                'message': '注册成功',
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': refresh_str,
                    'access': access_str,
                },
            }, status=status.HTTP_201_CREATED)
            set_auth_cookies(response, access=access_str, refresh=refresh_str)
            return response

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    """
    获取当前登录用户信息的视图。
    """
    permission_classes = [IsAuthenticated]  # 必须带上合法 Token 才能访问

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return Response({
            'user': serializer.data
        })

class DeleteAccountView(APIView):
    """
    删除当前登录用户账户 —— 硬删除（真正把 user_profiles 行从数据库里删掉）。

    User 上大部分反向 FK 是 CASCADE，所以这一步会把该用户的 FSRS 卡片、笔记本、
    学习计划、AI 题目、AT 币交易记录、购物车项、写作记录等一并连锁删除。
    上传到磁盘的头像和背景图先手动清一遍，避免磁盘悬挂文件。
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user

        # Clean up on-disk media before the row disappears. Skip external URLs
        # (bg_image_url is polymorphic — users can paste https:// links).
        for field in ('avatar_file', 'bg_image_url'):
            value = getattr(user, field, None)
            if value and not str(value).startswith(('http://', 'https://')):
                try:
                    if default_storage.exists(value):
                        default_storage.delete(value)
                except Exception as e:
                    print(f'[DeleteAccount] failed to delete {field}={value}: {e}')

        try:
            user.delete()
        except Exception as e:
            return Response({
                'error': 'DELETE_FAILED',
                'detail': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = Response({'message': 'ACCOUNT_DELETED'}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response

class AvatarUploadView(APIView):
    """
    上传用户头像的视图。
    只允许上传图片文件。
    """
    permission_classes = [IsAuthenticated]

    ALLOWED_IMAGE_TYPES = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp'
    }

    def validate_image(self, file):
        """验证上传文件是否为有效图片。"""
        # 检查文件类型
        file_type = mimetypes.guess_type(file.name)[0]
        if file_type not in self.ALLOWED_IMAGE_TYPES:
            return False, '不支持的文件类型，只允许上传图片文件(jpg, png, gif, webp)'

        # 检查文件大小（限制 5MB）
        max_size = 5 * 1024 * 1024  # 5MB
        if file.size > max_size:
            return False, '文件太大，最大支持 5MB'

        # 尝试打开图片验证是否为有效图片
        try:
            image = Image.open(file)
            image.verify()  # 验证图片完整性
            file.seek(0)  # 重置文件指针
            return True, '验证成功'
        except Exception:
            return False, '无效的图片文件'

    def process_image(self, image_file, user_id):
        """处理图片：调整大小并保存"""
        try:
            # 打开图片
            image = Image.open(image_file)

            # 转换为RGB（处理PNG透明度）
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            # 调整图片大小（最大 400x400）
            max_size = (400, 400)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 生成唯一文件名（统一使用 JPEG 扩展）
            original_file_extension = self.ALLOWED_IMAGE_TYPES[mimetypes.guess_type(image_file.name)[0]]
            file_uuid = uuid.uuid4().hex[:8]
            filename = f'avatars/user_{user_id}_{file_uuid}.jpg'
            relative_path = f'avatars/user_{user_id}_{file_uuid}.jpg'

            # 保存图片：统一转换为 JPEG 格式以保持一致
            img_io = io.BytesIO()
            image.save(img_io, format='JPEG', quality=85)
            img_io.seek(0)

            # 保存到存储
            file_path = default_storage.save(relative_path, ContentFile(img_io.read()))

            # DB stores the relative media key (e.g. "avatars/user_1_ab12.jpg").
            # Frontend composes the full URL with import.meta.env.VITE_MEDIA_BASE.
            # Never bake the host origin into the DB — that value differs
            # between dev / prod and the DB is shared.
            return True, file_path, file_path, None

        except Exception as e:
            return False, None, None, f'图片处理失败: {str(e)}'

    def post(self, request):
        """上传新头像。"""
        try:
            if 'avatar' not in request.FILES:
                return Response({
                    'error': '请选择要上传的图片文件'
                }, status=status.HTTP_400_BAD_REQUEST)

            avatar_file = request.FILES['avatar']
            user = request.user

            # 验证图片
            is_valid, message = self.validate_image(avatar_file)
            if not is_valid:
                return Response({
                    'error': message
                }, status=status.HTTP_400_BAD_REQUEST)

            # 处理并保存图片
            success, avatar_url, avatar_file_path, error_message = self.process_image(avatar_file, user.id)
            if not success:
                return Response({
                    'error': error_message
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 删除旧头像文件
            if user.avatar_file and default_storage.exists(user.avatar_file):
                try:
                    default_storage.delete(user.avatar_file)
                except Exception as e:
                    print(f"删除旧头像文件失败: {str(e)}")

            # 更新用户头像信息
            user.avatar_url = avatar_url
            user.avatar_file = avatar_file_path
            user.save()

            return Response({
                'message': '头像上传成功',
                'avatar_url': avatar_url,
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'error': '头像上传失败',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        """删除用户头像（恢复为默认头像）。"""
        try:
            user = request.user

            # 如果有头像文件，先删除文件
            if user.avatar_file and default_storage.exists(user.avatar_file):
                try:
                    default_storage.delete(user.avatar_file)
                except Exception as e:
                    # 记录日志但继续执行
                    print(f"删除头像文件失败: {str(e)}")

            # 更新用户信息
            user.avatar_url = None
            user.avatar_file = None
            user.save()

            return Response({
                'message': '头像已删除',
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'error': '删除头像失败',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserSettingsView(APIView):
    """
    更新用户设置的视图，包含 AI 生成重试次数等配置。
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        """
        更新用户设置
        请求数据示例:
        {
            "ai_generation_retry_count": 5,
        }
        """
        try:
            user = request.user
            
            update_fields = ['updated_at']
            
            # 处理 AI 生成重试次数
            if 'ai_generation_retry_count' in request.data:
                retry_count = request.data.get('ai_generation_retry_count')
                
                # 验证范围：0-10
                if not isinstance(retry_count, int) or retry_count < 0 or retry_count > 10:
                    return Response({
                        'error': 'AI生成重试次数必须是 0-10 之间的整数'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                user.ai_generation_retry_count = retry_count
                update_fields.append('ai_generation_retry_count')
                
            # 处理生词本目标
            if 'target_vocab_name' in request.data:
                user.target_vocab_name = request.data.get('target_vocab_name', '')
                update_fields.append('target_vocab_name')
                
            # 处理语言偏好
            if 'language_preference' in request.data:
                user.language_preference = request.data.get('language_preference', 'zh')
                update_fields.append('language_preference')
                
            # 处理 AI 提供商
            if 'ai_provider' in request.data:
                user.ai_provider = request.data.get('ai_provider', 'deepseek')
                update_fields.append('ai_provider')
                
            # 处理个人目标 (听说读写与考试日期)
            score_fields = ['target_listening', 'target_reading', 'target_writing', 'target_speaking']
            has_score_update = False
            for sf in score_fields:
                if sf in request.data:
                    val = request.data.get(sf)
                    if val is None or val == '':
                        setattr(user, sf, None)
                    else:
                        setattr(user, sf, float(val))
                    update_fields.append(sf)
                    has_score_update = True
                    
            if has_score_update:
                # 重新计算总分 (target_score)
                scores = [getattr(user, sf) for sf in score_fields if getattr(user, sf) is not None]
                if len(scores) == 4:
                    avg = sum(scores) / 4.0
                    import math
                    frac = avg - math.floor(avg)
                    if frac < 0.25:
                        user.target_score = math.floor(avg)
                    elif frac < 0.75:
                        user.target_score = math.floor(avg) + 0.5
                    else:
                        user.target_score = math.ceil(avg)
                else:
                    user.target_score = None
                update_fields.append('target_score')
                
            if 'exam_date' in request.data:
                val = request.data.get('exam_date')
                if val is None or val == '':
                    user.exam_date = None
                else:
                    user.exam_date = val
                update_fields.append('exam_date')
            
            # 保存所有更新
            user.save(update_fields=update_fields)
            
            return Response({
                'message': '用户设置更新成功',
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'error': '更新用户设置失败',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResetPasswordView(APIView):
    """通过用户名或邮箱重置密码。"""
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = request.data.get('identifier', '').strip()
        new_password = request.data.get('new_password', '').strip()

        if not identifier:
            return Response({'error': '请输入用户名或邮箱'}, status=status.HTTP_400_BAD_REQUEST)
        if not new_password or len(new_password) < 6:
            return Response({'error': '新密码至少6位'}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        user = None
        if '@' in identifier:
            user = User.objects.filter(email=identifier).first()
        if not user:
            user = User.objects.filter(username=identifier).first()

        if not user:
            return Response({'error': '未找到该用户'}, status=status.HTTP_404_NOT_FOUND)

        user.set_password(new_password)
        user.save(update_fields=['password', 'updated_at'])

        return Response({'message': '密码修改成功，请用新密码登录'}, status=status.HTTP_200_OK)


class ChangeUsernameView(APIView):
    """修改用户名，需消耗 10,000 AT 币。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        new_username = request.data.get('new_username', '').strip()
        user = request.user

        if not new_username:
            return Response({'error': '新用户名不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_username) > 30 or len(new_username) < 2:
            return Response({'error': '用户名长度需要 2-30 个字符'}, status=status.HTTP_400_BAD_REQUEST)
        if not new_username.replace('_', '').replace('-', '').isalnum():
            return Response({'error': '用户名只能包含字母、数字、下划线和连字符'}, status=status.HTTP_400_BAD_REQUEST)
        if new_username == user.username:
            return Response({'error': '新用户名与当前用户名一致'}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        if User.objects.filter(username=new_username).exists():
            return Response({'error': '该用户名已被使用'}, status=status.HTTP_400_BAD_REQUEST)

        COST = 10_000
        if user.at_balance < COST:
            return Response({'error': f'AT 币余额不足，需要 {COST:,} AT'}, status=status.HTTP_400_BAD_REQUEST)

        from api.models import TransactionRecord
        TransactionRecord.record(user, TransactionRecord.Currency.AT_COIN, -COST, '修改用户名')
        user.username = new_username
        user.save(update_fields=['username', 'updated_at'])

        return Response({
            'message': f'用户名已修改为 {new_username}，消耗 {COST:,} AT 币',
            'username': new_username,
            'at_balance': user.at_balance,
        })


class LogoutView(APIView):
    """End the session: rotate jwt_token_id so any stolen access token is dead,
    and wipe the auth cookies on the response.

    AllowAny because logout must succeed even when the incoming cookies are
    already stale — otherwise the browser is stuck with dead cookies and the
    user thinks logout is broken. When the caller *is* authenticated we still
    rotate jwt_token_id to invalidate any other sessions.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            user = request.user
            user.jwt_token_id = str(uuid.uuid4())
            user.save(update_fields=['jwt_token_id'])
        response = Response({'message': '已退出登录'}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response


class CookieAwareTokenRefreshView(APIView):
    """Refresh the access token.

    Reads the refresh JWT from either the request body (legacy clients) or the
    httpOnly cookie (browser sessions). On success, sets a fresh access cookie
    and rotates the CSRF cookie. The refresh cookie is unchanged because
    simple-jwt's default is not to rotate refresh tokens.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh') or request.COOKIES.get(REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response({'error': 'No refresh token'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_token)
            access_str = str(refresh.access_token)
        except (TokenError, InvalidToken) as e:
            return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({'access': access_str}, status=status.HTTP_200_OK)
        set_auth_cookies(response, access=access_str)
        return response