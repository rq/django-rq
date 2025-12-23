from django.urls import include, path

from .urls import urlpatterns as default_urls

urlpatterns = [
    *default_urls,
    path("django-rq", include("django_rq.urls")),
]
