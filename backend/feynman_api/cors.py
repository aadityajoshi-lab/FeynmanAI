from django.conf import settings
from django.http import HttpResponse


class AllowCorsMiddleware:
    """Small dependency-free CORS middleware for the local demo."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        origin = request.headers.get("Origin")
        if origin and origin in settings.CORS_ALLOWED_ORIGINS:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"
            response["Vary"] = "Origin"
        # Clerk bearer requests and anonymous-progress claiming both use
        # custom headers. Keep the explicit allow-list so credentials remain
        # constrained to the configured local origins while allowing the
        # browser preflight to reach DRF.
        response["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-CSRFToken, X-Requested-With, "
            "X-Learner-ID, X-Feynman-Anonymous-Learner"
        )
        response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response["Access-Control-Max-Age"] = "600"
        return response
