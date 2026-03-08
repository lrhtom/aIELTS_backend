from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'nickname')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return value

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

    class Meta:
        model = User
        # 除去了密码等敏感字段
        fields = (
            'id', 'username', 'email', 'nickname', 'avatar_url',
            'target_score', 'current_score', 'exam_date',
            'membership_tier', 'vip_expires_at', 'daily_ai_quota',
            'at_balance', 'atBalance', 'is_email_verified', 'last_login', 'date_joined'
        )
