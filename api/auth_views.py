from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import UserRegistrationSerializer, UserSerializer
import os
import mimetypes
from PIL import Image
import io
import uuid
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

User = get_user_model()

class UserRegistrationView(APIView):
    """
    处理用户注册请求的视图
    """
    permission_classes = [AllowAny] # 允许任何人访问

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # 注册成功后，直接为用户发放 Token，让其自动登录
            refresh = RefreshToken.for_user(user)
            return Response({
                'message': '注册成功',
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    """
    获取当前登录用户信息的视图
    """
    permission_classes = [IsAuthenticated] # 必须带上合法的 Token 才能访问

    def get(self, request):
        user = request.user
        serializer = UserSerializer(user)
        return Response({
            'user': serializer.data
        })

class DeleteAccountView(APIView):
    """
    删除当前登录用户账户的视图
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        try:
            user = request.user
            # 记录用户信息用于日志（可选）
            username = user.username
            email = user.email

            # 删除用户
            user.delete()

            return Response({
                'message': '账户已成功删除',
                'deleted_user': {
                    'username': username,
                    'email': email
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'error': '删除账户时出错',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AvatarUploadView(APIView):
    """
    上传用户头像的视图
    只允许上传图片文件
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
        """验证上传的文件是否为有效的图片"""
        # 检查文件类型
        file_type = mimetypes.guess_type(file.name)[0]
        if file_type not in self.ALLOWED_IMAGE_TYPES:
            return False, '不支持的文件类型，只允许上传图片文件(jpg, png, gif, webp)'

        # 检查文件大小（限制为5MB）
        max_size = 5 * 1024 * 1024  # 5MB
        if file.size > max_size:
            return False, '文件太大，最大支持5MB'

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

            # 调整图片大小（最大400x400）
            max_size = (400, 400)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 生成唯一文件名 - 统一使用JPEG扩展名
            original_file_extension = self.ALLOWED_IMAGE_TYPES[mimetypes.guess_type(image_file.name)[0]]
            file_uuid = uuid.uuid4().hex[:8]
            filename = f'avatars/user_{user_id}_{file_uuid}.jpg'
            relative_path = f'avatars/user_{user_id}_{file_uuid}.jpg'

            # 保存图片 - 统一转换为JPEG格式以保持一致性
            img_io = io.BytesIO()
            image.save(img_io, format='JPEG', quality=85)
            img_io.seek(0)

            # 保存到存储
            file_path = default_storage.save(relative_path, ContentFile(img_io.read()))

            # 构建URL（根据存储配置）
            if hasattr(settings, 'MEDIA_URL'):
                avatar_url = f"{settings.MEDIA_URL}{file_path}"
            else:
                # 默认使用相对路径
                avatar_url = f"/media/{file_path}"

            # 在开发环境中生成包含服务器地址的完整URL
            # 确保前端可以直接访问头像
            if settings.DEBUG:
                # 生成包含服务器地址的完整URL
                avatar_url = f"http://127.0.0.1:8000{avatar_url}"


            return True, avatar_url, file_path, None

        except Exception as e:
            return False, None, None, f'图片处理失败: {str(e)}'

    def post(self, request):
        """上传新头像"""
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
        """删除用户头像（恢复为默认头像）"""
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
