import re
import os

file_path = r'e:\code\web\work\aIELTS\frontend\src\i18n\translations.ts'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new auth blocks
zh_auth = """    auth: {
        loginTitle: '欢迎回来',
        loginSubtitle: '登录以继续您的 aIELTS 学习之旅',
        registerTitle: '创建新账号',
        registerSubtitle: '加入 aIELTS，全方位提升您的雅思能力',
        username: '用户名',
        email: '邮箱地址',
        password: '密码',
        confirmPassword: '确认密码',
        loginBtn: '登录',
        loggingIn: '登录中...',
        registerBtn: '注册账号',
        registering: '注册中...',
        noAccount: '还没有账号？',
        hasAccount: '已拥有账号？',
        toRegister: '立即注册',
        toLogin: '直接登录',
        backToHome: '返回主页',
        errorUnauthorized: '用户名或密码错误。',
        errorGeneral: '发生错误，请稍后重试。',
        errorPasswordMismatch: '两次输入的密码不一致。',
        errorRegisterTaken: '注册失败：用户名或邮箱可能已被使用。',
        verificationCode: '邮箱验证码',
        codePlaceholder: '请输入6位验证码',
        sendCode: '获取验证码',
        resendCode: '重新获取({n}s)',
        codeSent: '验证码已发送到你的邮箱，请查收',
        sendingCode: '发送中...',
        errorCodeInvalid: '验证码错误或已过期，请重新获取',
        errorEmailRequired: '请先填写用户名和邮箱地址',
        errorBanned: '账号异常，请联系管理员处理。',
        manualTitle: '使用手册',
        manualSearch: '搜索功能或页面...',
        manualEmpty: '未找到相关内容',
    },"""

en_auth = """    auth: {
        loginTitle: 'Welcome Back',
        loginSubtitle: 'Log in to continue your aIELTS learning journey',
        registerTitle: 'Create Account',
        registerSubtitle: 'Join aIELTS to master English and achieve your dreams',
        username: 'Username',
        email: 'Email Address',
        password: 'Password',
        confirmPassword: 'Confirm Password',
        loginBtn: 'Log In',
        loggingIn: 'Logging in...',
        registerBtn: 'Register',
        registering: 'Registering...',
        noAccount: "Don't have an account?",
        hasAccount: 'Already have an account?',
        toRegister: 'Sign up now',
        toLogin: 'Login here',
        backToHome: 'Back to Home',
        errorUnauthorized: 'Invalid username or password.',
        errorGeneral: 'An error occurred. Please try again later.',
        errorPasswordMismatch: 'Passwords do not match.',
        errorRegisterTaken: 'Registration failed: Username or email might be taken.',
        verificationCode: 'Verification Code',
        codePlaceholder: 'Enter 6-digit code',
        sendCode: 'Send Code',
        resendCode: 'Resend ({n}s)',
        codeSent: 'Code sent to your email, please check your inbox',
        sendingCode: 'Sending...',
        errorCodeInvalid: 'Invalid or expired code, please request a new one',
        errorEmailRequired: 'Please fill in username and email first',
        errorBanned: 'Account suspended. Please contact the administrator.',
        manualTitle: 'User Manual',
        manualSearch: 'Search features or pages...',
        manualEmpty: 'No results found',
    },"""

# Robust regex to find the auth blocks in zh and en
# We look for auth: { ... } after zh/en identifiers
content = re.sub(r'(const zh: Translations = \{[\s\S]*?)auth: \{[\s\S]*?\},', rf'\1{zh_auth}', content)
# For en, it's later in the file
content = re.sub(r'(const en: Translations = \{[\s\S]*?)auth: \{[\s\S]*?\},', rf'\1{en_auth}', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Success")
