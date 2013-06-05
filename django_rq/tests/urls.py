from django.conf.urls import patterns, include, url


urlpatterns = patterns('',
    (r'^django-rq/', include('django_rq.urls')),
    url(r'^success/$', 'django_rq.tests.views.success', name='success'),
    url(r'^error/$', 'django_rq.tests.views.error', name='error'),
)
