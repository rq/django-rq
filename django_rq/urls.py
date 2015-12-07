from django.conf.urls import url

from django_rq import views

urlpatterns = [
    url(r'^$',
        views.stats, name='rq_home'),
    url(r'^queues/(?P<queue_index>[\d]+)/$',
        views.jobs, name='rq_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/finished/$',
        views.finished_jobs, name='rq_finished_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/started/$',
        views.started_jobs, name='rq_started_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/deferred/$',
        views.deferred_jobs, name='rq_deferred_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/empty/$',
        views.clear_queue, name='rq_clear'),
    url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/$',
        views.job_detail, name='rq_job_detail'),
    url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/delete/$',
        views.delete_job, name='rq_delete_job'),
    url(r'^queues/actions/(?P<queue_index>[\d]+)/$',
        views.actions, name='rq_actions'),
    url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/requeue/$',
        views.requeue_job_view, name='rq_requeue_job'),
]
