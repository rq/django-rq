from django.conf.urls import url
from .views import stats, jobs, finished_jobs, started_jobs, deferred_jobs
from .views import clear_queue, job_detail, delete_job, actions, requeue_job_view


urlpatterns = [
    url(r'^$', stats, name='rq_home'),
    url(r'^queues/(?P<queue_index>[\d]+)/$', jobs, name='rq_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/finished/$',
        finished_jobs, name='rq_finished_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/started/$',
        started_jobs, name='rq_started_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/deferred/$',
        deferred_jobs, name='rq_deferred_jobs'),
    url(r'^queues/(?P<queue_index>[\d]+)/empty/$', clear_queue, name='rq_clear'),
    url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/$', job_detail,
        name='rq_job_detail'),
    url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/delete/$',
        delete_job, name='rq_delete_job'),
    url(r'^queues/actions/(?P<queue_index>[\d]+)/$',
        actions, name='rq_actions'),
    url(r'^queues/(?P<queue_index>[\d]+)/(?P<job_id>[-\w]+)/requeue/$',
        requeue_job_view, name='rq_requeue_job'),
]
