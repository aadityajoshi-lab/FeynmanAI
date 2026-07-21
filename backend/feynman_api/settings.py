from pathlib import Path
import base64
import json
import os
from dotenv import dotenv_values, load_dotenv
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
LOCAL_ENV = dotenv_values(BASE_DIR / ".env")


def configured(name: str, default: str = "") -> str:
    """Prefer the explicit local env file so an inherited host key cannot surprise the UI."""
    value = LOCAL_ENV.get(name)
    return str(value) if value is not None else os.getenv(name, default)


def _urlsafe_b64_int(value: object) -> int:
    encoded = str(value or "").strip()
    if not encoded:
        raise ValueError("missing JWK integer")
    padded = encoded + "=" * (-len(encoded) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded.encode("ascii")), "big")


def _jwk_to_public_pem(jwk: object) -> str:
    if not isinstance(jwk, dict) or str(jwk.get("kty") or "").upper() != "RSA":
        raise ValueError("only RSA public JWKs are supported")
    numbers = rsa.RSAPublicNumbers(_urlsafe_b64_int(jwk.get("e")), _urlsafe_b64_int(jwk.get("n")))
    return numbers.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _configured_clerk_jwt_key() -> str:
    encoded = configured("CLERK_JWT_KEY_B64", "").strip()
    if encoded:
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            return base64.b64decode(padded.encode("ascii"), validate=True).decode("utf-8").strip()
        except (UnicodeDecodeError, ValueError):
            return ""
    jwks_path = BASE_DIR / "clerk_jwks.json"
    if not jwks_path.exists():
        return ""
    try:
        document = json.loads(jwks_path.read_text(encoding="utf-8"))
        keys = document.get("keys") if isinstance(document, dict) else document
        if not isinstance(keys, list) or not keys:
            return ""
        return _jwk_to_public_pem(keys[0])
    except (OSError, ValueError, json.JSONDecodeError):
        return ""
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "feynman-dev-only-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in configured(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in configured(
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

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
    "OPTIONS": {"timeout": 30},
}}
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # SessionAuthentication performs CSRF validation for authenticated unsafe
    # requests. Anonymous registration/login remain usable; the frontend first
    # calls /api/v1/auth/csrf before its authenticated mutations.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "teachback.authentication.ClerkAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "UNAUTHENTICATED_USER": None,
}
CLERK_SECRET_KEY = configured("CLERK_SECRET_KEY", "")
CLERK_JWT_KEY = _configured_clerk_jwt_key()
CLERK_AUTHORIZED_PARTIES = [
    origin.strip()
    for origin in configured(
        "CLERK_AUTHORIZED_PARTIES",
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
LLM_PROVIDER = configured("LLM_PROVIDER", "qwen").lower()
OPENAI_MODEL = configured("OPENAI_MODEL", "gpt-5.6-terra-high")
OPENAI_API_KEY = configured("OPENAI_API_KEY", "")
OPENAI_BASE_URL = configured("OPENAI_BASE_URL", "")
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
MISTRAL_API_KEY = configured("MISTRAL_API_KEY", "")
MISTRAL_OCR_MODEL = configured("MISTRAL_OCR_MODEL", "mistral-ocr-4-0")
MISTRAL_OCR_URL = configured("MISTRAL_OCR_URL", "https://api.mistral.ai/v1/ocr")
MISTRAL_OCR_TIMEOUT_SECONDS = float(configured("MISTRAL_OCR_TIMEOUT_SECONDS", "180"))
# OpenMAIC-style notebook copilot fallback. Keep search credentials server-only.
TAVILY_API_KEY = configured("TAVILY_API_KEY", "")
TAVILY_BASE_URL = configured("TAVILY_BASE_URL", "https://api.tavily.com")
SEARXNG_BASE_URL = configured("SEARXNG_BASE_URL", "")
WEB_SEARCH_TIMEOUT_SECONDS = float(configured("WEB_SEARCH_TIMEOUT_SECONDS", "25"))
WEB_SOURCE_TIMEOUT_SECONDS = float(configured("WEB_SOURCE_TIMEOUT_SECONDS", "30"))
WEB_SOURCE_MAX_BYTES = int(configured("WEB_SOURCE_MAX_BYTES", str(25 * 1024 * 1024)))
# The bounded study-source endpoint validates uploads at 50 MiB. Keep the
# request parser just above that ceiling and spool larger files to disk rather
# than rejecting ordinary lecture PDFs before the endpoint can inspect them.
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
