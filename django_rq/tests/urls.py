from django.conf.urls import include, url
from django.contrib import admin

from django_rq.tests import views

urlpatterns = [
    url(r'^django-rq/', include('django_rq.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^success/$', views.success, name='success'),
    url(r'^error/$', views.error, name='error'),
]
