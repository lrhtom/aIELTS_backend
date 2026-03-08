from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserRegistrationSerializer, UserSerializer

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
