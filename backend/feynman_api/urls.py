from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("teachback.dynamic_urls")),
    path("api/v1/", include("teachback.urls")),
]
