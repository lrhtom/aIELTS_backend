"""
邮箱验证码服务
使用 Resend HTTP API 发送邮件，在内存 Cache 中存储验证码（5分钟有效）
"""
import os
import random
import string
import requests
from django.core.cache import cache
from django.contrib.auth import get_user_model

User = get_user_model()

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'onboarding@resend.dev')
CODE_EXPIRE_SECONDS = 300  # 5 minutes

def _generate_code(length=6) -> str:
    """生成指定长度的纯数字验证码"""
    return ''.join(random.choices(string.digits, k=length))

from .redis_client import get_redis

def _cache_key(email: str) -> str:
    return f'email_verify_code:{email.lower()}'

def send_verification_code(email: str, username: str) -> tuple[bool, str]:
    """
    发送验证码到邮箱。
    返回 (success: bool, message: str)
    """
    code = _generate_code()
    redis = get_redis()
    
    try:
        # 使用 Upstash Redis，过期时间单位为秒
        redis.set(_cache_key(email), code, ex=CODE_EXPIRE_SECONDS)
    except Exception as e:
        print(f"[EmailService] Redis error: {str(e)}")
        # 如果 Redis 失败，降级使用内存（可选，但通常 Redis 应该高可用）
        # 这里选择记录日志并继续尝试发送邮件，或者直接报错
        return False, f"Cache service error: {str(e)}"

    html_content = f"""
    <div style="font-family: 'Segoe UI', Roboto, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 40px 32px; background: #fff; border-radius: 16px; border: 1px solid #e8ecf0;">
        <h1 style="font-size: 24px; font-weight: 700; color: #1a1a2e; margin: 0 0 8px 0;">aIELTS 验证码</h1>
        <p style="color: #64748b; font-size: 15px; margin: 0 0 32px 0;">Hi <strong>{username}</strong>，感谢注册 aIELTS！</p>
        <div style="background: linear-gradient(135deg, #f0f5ff, #e8edff); border-radius: 12px; padding: 28px; text-align: center; margin-bottom: 24px;">
            <p style="color: #3b5bdb; font-size: 14px; margin: 0 0 8px 0; letter-spacing: 1px; text-transform: uppercase;">你的验证码</p>
            <p style="font-size: 48px; font-weight: 800; letter-spacing: 12px; color: #1a1a2e; margin: 0; font-variant-numeric: tabular-nums;">{code}</p>
        </div>
        <p style="color: #94a3b8; font-size: 13px; text-align: center; margin: 0;">验证码 <strong>5 分钟</strong>内有效，请勿泄露给他人。</p>
    </div>
    """

    try:
        resp = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f'Bearer {RESEND_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'from': EMAIL_FROM,
                'to': [email],
                'subject': f'【aIELTS】注册验证码: {code}',
                'html': html_content,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return True, 'Code sent successfully'
        else:
            # 针对 Resend Onboarding 常见错误的特殊处理
            error_data = resp.json() if resp.text.startswith('{') else {}
            if resp.status_code == 403 and 'onboarding@resend.dev' in EMAIL_FROM:
                return False, 'EMAIL_SERVICE_RESTRICTION: 使用测试域名只能向注册邮箱发送邮件，请在 Resend 验证域名并更新 EMAIL_FROM。'
            
            return False, f"Email service error ({resp.status_code}): {resp.text}"
    except Exception as e:
        return False, f'Network error: {str(e)}'

def verify_code(email: str, code: str) -> bool:
    """校验验证码是否正确，正确则立即清除"""
    try:
        redis = get_redis()
        stored = redis.get(_cache_key(email))
        # upstash-redis 返回的结果可能是 bytes 或 string，取决于配置，但通常是 string
        if stored and str(stored) == str(code):
            redis.delete(_cache_key(email))
            return True
    except Exception as e:
        print(f"[EmailService] Redis verify error: {str(e)}")
    return False
