from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'nickname')

    def validate(self, data):
        username = data.get('username')
        email = data.get('email')

        # 同时检查用户名和邮箱的唯一性
        if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
            # 这里抛出一个非字段相关的错误，前端可以统一通过 t.auth.errorRegisterTaken 展示
            # 也可以改为返回特定的字段错误，但用户要求“相同姓名或者邮箱都视作为有人注册”，统一提示更符合要求
            raise serializers.ValidationError("REGISTER_TAKEN")
        
        return data

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            nickname=validated_data.get('nickname', '')
        )
        return user

class UserSerializer(serializers.ModelSerializer):
    """
    用于返回给前端的用户详细信息
    """
    atBalance = serializers.IntegerField(source='at_balance', read_only=True)
    createdAt = serializers.DateTimeField(source='date_joined', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    aiGenerationRetryCount = serializers.IntegerField(source='ai_generation_retry_count')

    class Meta:
        model = User
        # 除去了密码等敏感字段
        fields = (
            'id', 'username', 'email', 'nickname', 'avatar_url',
            'target_score', 'current_score', 'exam_date',
            'membership_tier', 'vip_expires_at', 'daily_ai_quota',
            'at_balance', 'atBalance', 'is_email_verified', 'last_login', 'date_joined',
            'createdAt', 'updatedAt',
            'bg_color', 'bg_image_url', 'bg_blur', 'is_staff', 'is_superuser',
            'ai_generation_retry_count', 'aiGenerationRetryCount',
        )

from .models import Feedback

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ('id', 'username', 'title', 'content', 'is_resolved', 'created_at')
        read_only_fields = ('id', 'username', 'created_at')


class AdminUserManageSerializer(serializers.ModelSerializer):
    atBalance = serializers.IntegerField(source='at_balance', read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'is_staff', 'is_superuser',
            'is_active', 'is_banned', 'is_email_verified',
            'date_joined', 'last_login', 'at_balance', 'atBalance',
        )
        read_only_fields = fields
