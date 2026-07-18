from pathlib import Path
import os
from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
LOCAL_ENV = dotenv_values(BASE_DIR / ".env")


def configured(name: str, default: str = "") -> str:
    """Prefer the explicit local env file so an inherited host key cannot surprise the UI."""
    value = LOCAL_ENV.get(name)
    return str(value) if value is not None else os.getenv(name, default)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "feynman-dev-only-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "teachback",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "feynman_api.cors.AllowCorsMiddleware",
]
ROOT_URLCONF = "feynman_api.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "feynman_api.wsgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / "db.sqlite3",
}}
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}
LLM_PROVIDER = configured("LLM_PROVIDER", "fixture").lower()
OPENAI_MODEL = configured("OPENAI_MODEL", "gpt-5.6")
OPENAI_API_KEY = configured("OPENAI_API_KEY", "")
FIREWORKS_API_KEY = configured("FIREWORKS_API_KEY", "")
FIREWORKS_MODEL = configured("FIREWORKS_MODEL", "accounts/fireworks/models/qwen3p7-plus")
FIREWORKS_BASE_URL = configured("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
# A complete study module includes source-grounded explanations, visuals, and
# four assessment stages per topic. Qwen can need more than a minute for that
# structured response, so allow a longer provider window by default.
FIREWORKS_TIMEOUT_SECONDS = float(configured("FIREWORKS_TIMEOUT_SECONDS", "240"))
REMEDIATION_VIDEO_PROVIDER = configured("REMEDIATION_VIDEO_PROVIDER", "fireworks-slides").lower()
VIDEO_SERVICE_BASE_URL = configured("VIDEO_SERVICE_BASE_URL", "http://127.0.0.1:3000")
VIDEO_SERVICE_KEY = configured("VIDEO_SERVICE_KEY", "feynman-local-video")
VIDEO_SERVICE_TIMEOUT_SECONDS = float(configured("VIDEO_SERVICE_TIMEOUT_SECONDS", "900"))
TTS_VOXCPM_BASE_URL = configured("TTS_VOXCPM_BASE_URL", "")
TTS_VOXCPM_API_KEY = configured("TTS_VOXCPM_API_KEY", "")
TTS_VOXCPM_TIMEOUT_SECONDS = float(configured("TTS_VOXCPM_TIMEOUT_SECONDS", "90"))
TTS_VOXCPM_PROMPT = configured("TTS_VOXCPM_PROMPT", "natural, clear engineering classroom voice")
# The bounded study-source endpoint validates uploads at 50 MiB. Keep the
# request parser just above that ceiling and spool larger files to disk rather
# than rejecting ordinary lecture PDFs before the endpoint can inspect them.
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
