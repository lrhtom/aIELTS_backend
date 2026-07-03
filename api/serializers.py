from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'nickname')

    def validate(self, data):
        username = data.get('username')
        email = (data.get('email') or '').strip().lower() or None
        data['email'] = email  # normalise for create()

        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError("REGISTER_TAKEN")
        # Email uniqueness only when provided — empty email is allowed for many users.
        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError("REGISTER_TAKEN")

        return data

    def create(self, validated_data):
        # DO NOT use `User.objects.create_user()`. It normalises None → "",
        # then INSERTs with `email=""`. MySQL's UNIQUE(email) collides on the
        # second emailless registration ("Duplicate entry '' for key
        # 'user_profiles.email'"). We construct the row directly so the
        # column receives NULL, which multiple rows can hold under UNIQUE.
        email_val = validated_data.get('email') or None
        user = User(
            username=validated_data['username'],
            email=email_val,
            nickname=validated_data.get('nickname', ''),
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

class UserSerializer(serializers.ModelSerializer):
    """
    用于返回给前端的用户详细信息
    """
    atBalance = serializers.IntegerField(source='at_balance', read_only=True)
    createdAt = serializers.DateTimeField(source='date_joined', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    aiGenerationRetryCount = serializers.IntegerField(source='ai_generation_retry_count')

    targetVocabName = serializers.CharField(source='target_vocab_name', read_only=True)
    languagePreference = serializers.CharField(source='language_preference', read_only=True)
    aiProvider = serializers.CharField(source='ai_provider', read_only=True)

    class Meta:
        model = User
        # 除去了密码等敏感字段
        fields = (
            'id', 'username', 'email', 'nickname', 'avatar_url',
            'target_score', 'target_listening', 'target_reading', 'target_writing', 'target_speaking',
            'current_score', 'exam_date',
            'membership_tier', 'vip_expires_at', 'daily_ai_quota',
            'at_balance', 'atBalance', 'is_email_verified', 'last_login', 'date_joined',
            'createdAt', 'updatedAt',
            'bg_color', 'bg_image_url', 'bg_blur', 'is_staff', 'is_superuser',
            'ai_generation_retry_count', 'aiGenerationRetryCount',
            'target_vocab_name', 'targetVocabName',
            'language_preference', 'languagePreference',
            'ai_provider', 'aiProvider',
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

from .models import UserTodoItem, UserShortcut

class UserTodoItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTodoItem
        fields = ['id', 'text', 'done', 'created_at']
        read_only_fields = ['id', 'created_at']

class UserShortcutSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserShortcut
        fields = ['id', 'title', 'url', 'open_in_new_tab', 'created_at']
        read_only_fields = ['id', 'created_at']
