"""
Django settings for gimpo365-inventory (config project).

환경 설정은 환경변수(.env)로 관리한다. (TECH_SPEC §15.3)
DB는 PostgreSQL만 사용한다. SQLite는 사용하지 않는다. (TECH_SPEC §0, §15.1)
"""

from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 환경변수 로딩
# ---------------------------------------------------------------------------
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# .env 파일이 있으면 읽는다. (없어도 환경변수로 동작)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)


# ---------------------------------------------------------------------------
# 보안 / 기본
# ---------------------------------------------------------------------------
# SECURITY WARNING: 운영 환경에서는 반드시 환경변수로 SECRET_KEY를 주입한다.
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-me-in-production",
)

DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")


# ---------------------------------------------------------------------------
# 애플리케이션
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 로컬 앱
    "core",
    "accounts",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "inventory.context_processors.nav_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# 데이터베이스 (PostgreSQL 전용)
# ---------------------------------------------------------------------------
# SQLite는 사용하지 않는다. ENGINE을 PostgreSQL로 고정한다. (TECH_SPEC §0)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="gimpo365_inventory"),
        "USER": env("POSTGRES_USER", default="postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="postgres"),
        "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}


# ---------------------------------------------------------------------------
# 비밀번호 검증
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ---------------------------------------------------------------------------
# 국제화 / 시간대
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "ko-kr"

TIME_ZONE = "Asia/Seoul"

USE_I18N = True

USE_TZ = True


# ---------------------------------------------------------------------------
# 정적 파일
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# ---------------------------------------------------------------------------
# 기본 PK 타입
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# 인증 / 로그인 흐름
# ---------------------------------------------------------------------------
# Custom User. 첫 migration 전 확정. (TECH_SPEC §0, §4)
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"

# ---------------------------------------------------------------------------
# 세션 정책 (v0.2.1) — 공용/원내 PC 로그인 유지 문제 완화
# ---------------------------------------------------------------------------
# - 비활동 2시간 후 세션 만료 (사용 중이면 매 요청마다 만료시각이 연장된다)
# - 브라우저 종료 시 세션 만료
SESSION_COOKIE_AGE = 60 * 60 * 2
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
