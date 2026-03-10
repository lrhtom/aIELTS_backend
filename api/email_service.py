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

def _cache_key(email: str) -> str:
    return f'email_verify_code:{email.lower()}'

def send_verification_code(email: str, username: str) -> tuple[bool, str]:
    """
    发送验证码到邮箱。
    返回 (success: bool, message: str)
    """
    code = _generate_code()
    cache.set(_cache_key(email), code, timeout=CODE_EXPIRE_SECONDS)

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
            return False, f'Email service error: {resp.text}'
    except Exception as e:
        return False, f'Network error: {str(e)}'

def verify_code(email: str, code: str) -> bool:
    """校验验证码是否正确，正确则立即清除"""
    stored = cache.get(_cache_key(email))
    if stored and stored == code:
        cache.delete(_cache_key(email))
        return True
    return False
