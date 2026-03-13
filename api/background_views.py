from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .serializers import UserSerializer
import mimetypes
import io
import uuid
from PIL import Image
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings


def _delete_media_file(url_or_path: str):
    """删除 media 目录下的文件，接受完整 URL 或相对路径，失败时仅打印日志"""
    if not url_or_path:
        return
    path = url_or_path
    for prefix in [f'http://127.0.0.1:8000{settings.MEDIA_URL}', settings.MEDIA_URL]:
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    if path and default_storage.exists(path):
        try:
            default_storage.delete(path)
        except Exception as e:
            print(f'[media] 删除文件失败 {path}: {e}')


class BackgroundSettingsView(APIView):
    """
    获取 / 更新用户背景偏好设置
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'bg_color': user.bg_color or '',
            'bg_image_url': user.bg_image_url or '',
            'bg_blur': user.bg_blur if user.bg_blur is not None else 2.0,
        })

    def patch(self, request):
        user = request.user
        data = request.data

        if 'bg_color' in data:
            val = data['bg_color'] or None
            user.bg_color = val if val != '' else None

        if 'bg_image_url' in data:
            old_url = user.bg_image_url
            val = data['bg_image_url'] or None
            new_val = val if val != '' else None
            user.bg_image_url = new_val
            # 仅删除自己上传的文件（URL 含 bg_images/ 标志），外链不处理
            if old_url and 'bg_images/' in old_url and new_val != old_url:
                _delete_media_file(old_url)

        if 'bg_blur' in data:
            try:
                blur_val = float(data['bg_blur'])
                user.bg_blur = max(0.0, min(20.0, blur_val))
            except (TypeError, ValueError):
                pass

        user.save(update_fields=['bg_color', 'bg_image_url', 'bg_blur'])

        return Response({
            'message': '背景设置已保存',
            'bg_color': user.bg_color or '',
            'bg_image_url': user.bg_image_url or '',
            'user': UserSerializer(user).data,
        })


class BackgroundImageUploadView(APIView):
    """
    上传背景图片，返回可持久化 URL
    """
    permission_classes = [IsAuthenticated]

    ALLOWED_TYPES = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/webp': 'webp',
    }
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB

    def post(self, request):
        if 'image' not in request.FILES:
            return Response({'error': '请选择要上传的图片'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['image']
        user = request.user

        # 验证类型
        mime = mimetypes.guess_type(file.name)[0]
        if mime not in self.ALLOWED_TYPES:
            return Response({'error': '不支持的文件类型，仅支持 jpg/png/gif/webp'}, status=status.HTTP_400_BAD_REQUEST)

        # 验证大小
        if file.size > self.MAX_SIZE:
            return Response({'error': '图片不能超过 10MB'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 处理图片 — 限制最大分辨率为 2560x1440 防止超大图
            img = Image.open(file)
            img.verify()
            file.seek(0)
            img = Image.open(file)

            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            max_w, max_h = 2560, 1440
            if img.width > max_w or img.height > max_h:
                img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

            # 保存
            uid = uuid.uuid4().hex[:10]
            filename = f'bg_images/user_{user.id}_{uid}.jpg'
            img_io = io.BytesIO()
            img.save(img_io, format='JPEG', quality=88)
            img_io.seek(0)
            saved_path = default_storage.save(filename, ContentFile(img_io.read()))

            # 构建 URL
            if settings.DEBUG:
                image_url = f'http://127.0.0.1:8000{settings.MEDIA_URL}{saved_path}'
            else:
                image_url = f'{settings.MEDIA_URL}{saved_path}'

            # 直接写入用户记录
            old_url = user.bg_image_url
            user.bg_image_url = image_url
            user.bg_color = None  # 图片优先，清除颜色设置
            user.save(update_fields=['bg_image_url', 'bg_color'])

            # 删除旧背景图文件
            if old_url and 'bg_images/' in old_url:
                _delete_media_file(old_url)

            return Response({
                'message': '背景图片上传成功',
                'image_url': image_url,
                'user': UserSerializer(user).data,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': f'图片处理失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
