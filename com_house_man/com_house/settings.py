"""Django settings for the Companies House enrichment app."""

import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

DEBUG = os.environ.get("DEBUG", "False").strip().lower() in {"1", "true", "yes", "on"}

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "dev-only-secret-key"
if not DEBUG and SECRET_KEY == "dev-only-secret-key":
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DEBUG is False.")

_allowed_hosts_raw = os.environ.get("ALLOWED_HOSTS", "")
if _allowed_hosts_raw:
    ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts_raw.split(",") if host.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
else:
    ALLOWED_HOSTS = []

for _railway_host in (
    os.environ.get("RAILWAY_PUBLIC_DOMAIN", ""),
    os.environ.get("RAILWAY_PRIVATE_DOMAIN", ""),
):
    host = _railway_host.strip()
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Set ALLOWED_HOSTS or deploy on Railway with RAILWAY_PUBLIC_DOMAIN set."
    )

COMPANIES_HOUSE_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
if not DEBUG and not COMPANIES_HOUSE_API_KEY:
    raise ImproperlyConfigured("Set COMPANIES_HOUSE_API_KEY when DEBUG is False.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "com_house.urls"

_context_processors = [
    "django.template.context_processors.request",
    "django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages",
    "core.context_processors.teletext_context",
]
if DEBUG:
    _context_processors.insert(0, "django.template.context_processors.debug")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": _context_processors,
        },
    },
]

WSGI_APPLICATION = "com_house.wsgi.application"


def _database_url():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    db_host = os.environ.get("DB_HOST") or os.environ.get("PGHOST")
    db_name = os.environ.get("DB_NAME") or os.environ.get("PGDATABASE")
    db_user = os.environ.get("DB_USER") or os.environ.get("PGUSER")
    db_password = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD")
    db_port = os.environ.get("DB_PORT") or os.environ.get("PGPORT", "5432")

    if all([db_host, db_name, db_user, db_password]):
        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    if DEBUG:
        return f"sqlite:///{BASE_DIR / 'db.sqlite3'}"

    raise ImproperlyConfigured(
        "Set DATABASE_URL or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD "
        "(or Railway PGHOST/PGDATABASE/PGUSER/PGPASSWORD) when DEBUG is False."
    )


DATABASES = {
    "default": dj_database_url.config(
        default=_database_url(),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Railway terminates TLS at the edge; internal healthchecks use plain HTTP.
    _on_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    _local_only = set(ALLOWED_HOSTS) <= {"localhost", "127.0.0.1", "[::1]"}
    SECURE_SSL_REDIRECT = (
        not _on_railway
        and not _local_only
        and os.environ.get("SECURE_SSL_REDIRECT", "true").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": sys.stdout,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "core": {
            "handlers": ["console"],
            "level": os.environ.get("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
