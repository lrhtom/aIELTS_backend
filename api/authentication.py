from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from django.conf import settings

class SingleDeviceJWTAuthentication(JWTAuthentication):
    """
    自定义 JWT 认证类：除了校验 Token 签名和过期时间外，
    还要校验 Token 内含的 jwt_token_id 是否与数据库中存储的一致。
    """
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        
        # 获取 Token 中携带的 jwt_token_id
        token_id_in_jwt = validated_token.get('jwt_token_id')
        
        # 如果 Token 里没有该 ID（旧 Token）或者与数据库不符，则视为失效
        if not token_id_in_jwt or str(user.jwt_token_id) != str(token_id_in_jwt):
            raise AuthenticationFailed('该账号已在其他设备登录，请重新登录', code='token_invalidated')
            
        return user
