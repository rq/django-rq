import django
from django_rq import views

# Fixed supporting for Django 2.0 and greater
# See: https://docs.djangoproject.com/en/2.0/ref/urls/#django.urls.re_path
if django.VERSION[0] >= 2:
    from django.urls import re_path

    urlpatterns = [
        re_path(r'^$',
                views.stats, name='rq_home'),
        re_path(r'^stats.json/(?P<token>[\w]+)?/?$',
                views.stats_json, name='rq_home_json'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/$',
                views.jobs, name='rq_jobs'),
        re_path(r'^workers/(?P<queue_index>[\d]+)/$',
                views.workers, name='rq_workers'),
        re_path(r'^workers/(?P<queue_index>[\d]+)/(?P<key>[-\w\.\:]+)/$',
                views.worker_details, name='rq_worker_details'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/finished/$',
                views.finished_jobs, name='rq_finished_jobs'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/started/$',
                views.started_jobs, name='rq_started_jobs'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/deferred/$',
                views.deferred_jobs, name='rq_deferred_jobs'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/empty/$',
                views.clear_queue, name='rq_clear'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/requeue-all/$',
                views.requeue_all, name='rq_requeue_all'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/$',
                views.job_detail, name='rq_job_detail'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/delete/$',
                views.delete_job, name='rq_delete_job'),
        re_path(r'^queues/actions/(?P<queue_index>[\d]+)/$',
                views.actions, name='rq_actions'),
        re_path(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/requeue/$',
                views.requeue_job_view, name='rq_requeue_job'),
    ]

# Fallback for Django 1.11 and lower
if django.VERSION[0] == 1:
    from django.conf.urls import url

    urlpatterns = [
        url(r'^$',
            views.stats, name='rq_home'),
        url(r'^stats.json/(?P<token>[\w]+)?/?$',
            views.stats_json, name='rq_home_json'),
        url(r'^queues/(?P<queue_index>[\d]+)/$',
            views.jobs, name='rq_jobs'),
        url(r'^workers/(?P<queue_index>[\d]+)/$',
            views.workers, name='rq_workers'),
        url(r'^workers/(?P<queue_index>[\d]+)/(?P<key>[-\w\.\:]+)/$',
            views.worker_details, name='rq_worker_details'),
        url(r'^queues/(?P<queue_index>[\d]+)/finished/$',
            views.finished_jobs, name='rq_finished_jobs'),
        url(r'^queues/(?P<queue_index>[\d]+)/started/$',
            views.started_jobs, name='rq_started_jobs'),
        url(r'^queues/(?P<queue_index>[\d]+)/deferred/$',
            views.deferred_jobs, name='rq_deferred_jobs'),
        url(r'^queues/(?P<queue_index>[\d]+)/empty/$',
            views.clear_queue, name='rq_clear'),
        url(r'^queues/(?P<queue_index>[\d]+)/requeue-all/$',
            views.requeue_all, name='rq_requeue_all'),
        url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/$',
            views.job_detail, name='rq_job_detail'),
        url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/delete/$',
            views.delete_job, name='rq_delete_job'),
        url(r'^queues/actions/(?P<queue_index>[\d]+)/$',
            views.actions, name='rq_actions'),
        url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/requeue/$',
            views.requeue_job_view, name='rq_requeue_job'),
    ]
