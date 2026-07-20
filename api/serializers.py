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
        # 新用户注册赠送 1 张补签卡
        from api.models import UserItem
        UserItem.grant(user, UserItem.ItemType.MAKEUP_CARD, 1)
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


from .models import SurveyResponse

class SurveySerializer(serializers.ModelSerializer):
    """问卷提交 + 管理端读取共用。

    Part B 的 8 项评分必填且必须为 1-5；Part A / Part C 可选。username/user 由
    视图在 perform_create 时注入，前端不可写。
    """

    # Part B 评分字段（必须 1-5）
    RATING_FIELDS = (
        'q_all_skills', 'q_reading_relevant', 'q_listening_clear',
        'q_speaking_anxiety', 'q_writing_feedback', 'q_vocab_memory',
        'q_easy_navigate', 'q_recommend',
    )
    PREP_DURATION_CHOICES = {'', 'lt1m', '1to3m', '3to6m', '6mplus'}
    TARGET_BAND_CHOICES = {'', '5.5-6.0', '6.5', '7.0', '7.5+'}

    class Meta:
        model = SurveyResponse
        fields = (
            'id', 'username',
            'prep_duration', 'target_band',
            'q_all_skills', 'q_reading_relevant', 'q_listening_clear',
            'q_speaking_anxiety', 'q_writing_feedback', 'q_vocab_memory',
            'q_easy_navigate', 'q_recommend',
            'most_useful', 'improvements', 'other_comments',
            'created_at',
        )
        read_only_fields = ('id', 'username', 'created_at')

    def validate_prep_duration(self, value):
        if value not in self.PREP_DURATION_CHOICES:
            raise serializers.ValidationError('SURVEY_INVALID_PREP_DURATION')
        return value

    def validate_target_band(self, value):
        if value not in self.TARGET_BAND_CHOICES:
            raise serializers.ValidationError('SURVEY_INVALID_TARGET_BAND')
        return value

    def validate(self, data):
        # Part B 全部必填、范围 1-5。用 partial 更新（管理端不会走此序列化器写入）也安全。
        for f in self.RATING_FIELDS:
            v = data.get(f)
            if v is None or not (1 <= int(v) <= 5):
                raise serializers.ValidationError({f: 'SURVEY_RATING_REQUIRED'})
        return data


class AdminUserManageSerializer(serializers.ModelSerializer):
    atBalance = serializers.IntegerField(source='at_balance', read_only=True)
    lastIp = serializers.CharField(source='last_ip', read_only=True, allow_null=True)
    isIpBanned = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'is_staff', 'is_superuser',
            'is_active', 'is_banned', 'is_email_verified',
            'date_joined', 'last_login', 'at_balance', 'atBalance',
            'last_ip', 'lastIp', 'isIpBanned',
        )
        read_only_fields = fields

    def get_isIpBanned(self, obj) -> bool:
        # Cheap per-row lookup — admin list is ≤ 20/page. Prefetch into a set()
        # in the view if this list ever gets much bigger.
        if not obj.last_ip:
            return False
        from .models import BannedIP
        return BannedIP.objects.filter(ip_address=obj.last_ip).exists()

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
