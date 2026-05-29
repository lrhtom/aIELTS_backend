"""
Django settings for backend project.
"""
import os
import socket
from pathlib import Path
from dotenv import load_dotenv
from corsheaders.defaults import default_headers

# 加载 .env
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

import pymysql
pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-change-in-production-xxxxxxxxxx'
    else:
        raise RuntimeError('DJANGO_SECRET_KEY environment variable is required in production')

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# CORS — 允许前端开发服务器跨域
CORS_ALLOW_ALL_ORIGINS = DEBUG  # 仅在开发模式下允许所有来源
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]
# 生产环境前端地址（ClawCloud / 自定义域名）
if os.environ.get('CORS_ORIGIN'):
    CORS_ALLOWED_ORIGINS.append(os.environ['CORS_ORIGIN'])

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-ai-provider",
    "ngrok-skip-browser-warning",
    "x-mcp-request-id",
    "cache-control",
    "pragma",
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'


def _get_database_host() -> str:
    host = os.environ.get('DB_HOST', 'localhost').strip()
    fallback_host = os.environ.get('DB_HOST_FALLBACK', '').strip()

    if not fallback_host:
        return host

    try:
        socket.getaddrinfo(host, int(os.environ.get('DB_PORT', '3306')), 0, socket.SOCK_STREAM)
        return host
    except socket.gaierror:
        # Allow explicit fallback host (usually a fixed DB IP) when DNS is unstable.
        return fallback_host


def _get_database_ssl_options() -> dict:
    ca_path_raw = os.environ.get('DB_SSL_CA', '').strip()
    if not ca_path_raw:
        return {}

    ca_path = Path(ca_path_raw)
    if not ca_path.is_absolute():
        ca_path = (BASE_DIR / ca_path).resolve()

    if ca_path.exists() and ca_path.is_file():
        return {'ca': str(ca_path)}

    # Avoid startup/request crashes when DB_SSL_CA points to a missing file.
    print(f"[settings] DB_SSL_CA not found: {ca_path_raw}. Falling back to default SSL context.")
    return {}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': _get_database_host(),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'NAME': os.environ.get('DB_NAME', 'aielts_db'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'ssl': _get_database_ssl_options(),
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# 媒体文件配置
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'api.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'api.core.authentication.SingleDeviceJWTAuthentication',
    ),
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
}
