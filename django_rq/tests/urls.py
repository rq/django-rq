from django.contrib import admin
from django.urls import path

from django_rq.urls import urlpatterns as django_rq_urlpatterns

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('success/', views.success, name='success'),
    path('error/', views.error, name='error'),
    path('django-rq/', (django_rq_urlpatterns, '', 'django_rq')),
]
