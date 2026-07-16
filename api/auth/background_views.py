from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from api.serializers import UserSerializer
import mimetypes
import io
import uuid
from PIL import Image
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings


def _delete_media_file(key_or_url: str):
    """Delete a locally-uploaded media file.

    Accepts either a relative storage key (`bg_images/user_1_abc.jpg`) —
    the new canonical form written to DB — or a legacy full URL that still
    contains one of the historical `…/media/` prefixes (kept for one release
    while old rows heal via migration).

    External http(s):// URLs (user-pasted image links) are silently ignored;
    we never delete files we didn't upload.
    """
    if not key_or_url:
        return
    path = key_or_url
    # Legacy heal: strip prefixes if they leaked through before migration ran.
    legacy_prefixes = (
        'http://127.0.0.1:8000/media/',
        'http://47.85.195.208:8000/media/',
        'https://47.85.195.208:8000/media/',
        settings.MEDIA_URL,  # "/media/" — for relative-URL legacy rows
    )
    for prefix in legacy_prefixes:
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    # If path still looks like an external URL, it isn't ours.
    if path.startswith(('http://', 'https://')):
        return
    if path and default_storage.exists(path):
        try:
            default_storage.delete(path)
        except Exception as e:
            print(f'[media] 删除文件失败 {path}: {e}')


class BackgroundSettingsView(APIView):
    """
    获取 / 更新用户背景偏好设置。
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
            # 仅删除自己上传的文件（URL 含 bg_images/ 标记），外链不处理。
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
    上传背景图片，返回可持久化 URL。
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
            # 处理图片：限制最大分辨率 2560x1440，避免超大图。
            img = Image.open(file)
            img.verify()
            file.seek(0)
            img = Image.open(file)

            uid = uuid.uuid4().hex[:10]
            if img.format == 'GIF' and getattr(img, 'is_animated', False):
                # 多帧 GIF 原样保存：JPEG 重编码只保留第一帧，动画丢失。
                # 体积上限由 MAX_SIZE 控制（10MB），不做分辨率压缩。
                file.seek(0)
                filename = f'bg_images/user_{user.id}_{uid}.gif'
                saved_path = default_storage.save(filename, ContentFile(file.read()))
            else:
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

                filename = f'bg_images/user_{user.id}_{uid}.jpg'
                img_io = io.BytesIO()
                img.save(img_io, format='JPEG', quality=88)
                img_io.seek(0)
                saved_path = default_storage.save(filename, ContentFile(img_io.read()))

            # DB stores the relative media key only. The frontend prepends
            # VITE_MEDIA_BASE to build the final URL. This lets dev and prod
            # (which share the Aiven DB but have different origins) both
            # resolve the same row without polluting each other.
            old_key = user.bg_image_url
            user.bg_image_url = saved_path
            user.bg_color = None  # 图片优先，清除纯色背景
            user.save(update_fields=['bg_image_url', 'bg_color'])

            # 删除旧背景图文件（仅当上一版是自己上传的，判别标志是含 bg_images/）
            if old_key and 'bg_images/' in old_key:
                _delete_media_file(old_key)

            return Response({
                'message': '背景图片上传成功',
                'image_url': saved_path,
                'user': UserSerializer(user).data,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': f'图片处理失败: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


