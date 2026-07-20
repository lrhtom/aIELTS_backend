from rest_framework import generics, permissions
from api.models import Feedback, SurveyResponse
from api.serializers import FeedbackSerializer, SurveySerializer

class FeedbackCreateView(generics.CreateAPIView):
    """
    用户提交 Bug 反馈的接口。
    """
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # 自动关联当前登录用户的用户名
        serializer.save(username=self.request.user.username)


class SurveyCreateView(generics.CreateAPIView):
    """
    用户提交问卷调查的接口（允许同一用户多次提交）。
    """
    queryset = SurveyResponse.objects.all()
    serializer_class = SurveySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # user FK + username 均由当前登录用户注入，前端不可伪造。
        serializer.save(user=self.request.user, username=self.request.user.username)


