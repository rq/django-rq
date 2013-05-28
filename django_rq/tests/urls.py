from django.conf.urls import patterns, include


urlpatterns = patterns('',
    (r'^django-rq/', include('django_rq.urls')),
)
