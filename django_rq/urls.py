from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('django_rq.views',
    url(r'^$', 'stats', name='django_rq_statistics'),
)
