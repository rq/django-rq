"""URL configuration for the standalone RQ Dashboard."""
from django.contrib import admin
from django.urls import include, path

from django_rq.urls import urlpatterns as django_rq_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(django_rq_urlpatterns)),
]
