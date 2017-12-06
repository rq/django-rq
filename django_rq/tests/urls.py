from django.conf.urls import include, url
from django.contrib import admin

from django_rq.tests import views
from django_rq.urls import urlpatterns

urlpatterns = [
    url(r'^django-rq/', (urlpatterns, '', 'django_rq')),
    url(r'^admin/', admin.site.urls),
    url(r'^success/$', views.success, name='success'),
    url(r'^error/$', views.error, name='error'),
]
