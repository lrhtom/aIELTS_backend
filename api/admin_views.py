from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import Feedback
from .serializers import FeedbackSerializer, AdminUserManageSerializer

User = get_user_model()

class AdminFeedbackPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminUserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class IsAdminUser(permissions.BasePermission):
    """
    仅限管理员（is_staff）访问
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)

class AdminFeedbackListView(generics.ListAPIView):
    """
    管理员查看所有反馈的接口（分页）
    """
    queryset = Feedback.objects.all().order_by('-created_at')
    serializer_class = FeedbackSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminFeedbackPagination

class AdminFeedbackUpdateView(generics.UpdateAPIView):
    """
    管理员更新反馈状态（如标记解决）
    """
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [IsAdminUser]
    
    def patch(self, request, *args, **kwargs):
        # 仅允许更新 is_resolved 字段
        instance = self.get_object()
        is_resolved = request.data.get('is_resolved')
        if is_resolved is not None:
            instance.is_resolved = is_resolved
            instance.save()
            return Response(FeedbackSerializer(instance).data)
        return Response({"error": "Missing is_resolved field"}, status=status.HTTP_400_BAD_REQUEST)

class AdminFeedbackDeleteView(generics.DestroyAPIView):
    """
    管理员删除反馈记录
    """
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [IsAdminUser]


class AdminUserListView(generics.ListAPIView):
    """
    管理员查看用户列表（分页）
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserManageSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminUserPagination


class AdminUserBanToggleView(APIView):
    """
    管理员封禁/解封用户
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.is_staff or target_user.is_superuser:
            return Response({'error': 'CANNOT_MODIFY_ADMIN'}, status=status.HTTP_403_FORBIDDEN)

        is_banned = request.data.get('is_banned')
        if is_banned is None:
            return Response({'error': 'MISSING_IS_BANNED'}, status=status.HTTP_400_BAD_REQUEST)

        target_user.is_banned = bool(is_banned)
        target_user.save(update_fields=['is_banned', 'updated_at'])
        return Response(AdminUserManageSerializer(target_user).data, status=status.HTTP_200_OK)


class AdminUserDeleteView(APIView):
    """
    管理员删除用户
    """
    permission_classes = [IsAdminUser]

    def delete(self, request, pk: int):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.is_staff or target_user.is_superuser:
            return Response({'error': 'CANNOT_MODIFY_ADMIN'}, status=status.HTTP_403_FORBIDDEN)

        target_user.delete()
        return Response({'message': 'USER_DELETED'}, status=status.HTTP_200_OK)
