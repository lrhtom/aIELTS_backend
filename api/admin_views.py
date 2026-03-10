from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import Feedback
from .serializers import FeedbackSerializer

class AdminPagination(PageNumberPagination):
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
    pagination_class = AdminPagination

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
