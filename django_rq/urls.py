from django.urls import path, re_path

from . import stats_views, views
from .contrib.prometheus import RQCollector

metrics_view = (
    [
        re_path(r'^metrics/?$', stats_views.prometheus_metrics, name='rq_metrics'),
    ]
    if RQCollector is not None
    else []
)

urlpatterns = [
    path('', stats_views.stats, name='rq_home'),
    re_path(r'^stats.json/?$', stats_views.stats_json, name='rq_home_json'),
    re_path(r'^stats.json/(?P<token>[\w]+)?/?$', stats_views.stats_json, name='rq_home_json'),
    *metrics_view,
    path('queues/<int:queue_index>/', views.jobs, name='rq_jobs'),
    path('workers/<int:queue_index>/', views.workers, name='rq_workers'),
    path('workers/<int:queue_index>/<str:key>/', views.worker_details, name='rq_worker_details'),
    path('queues/<int:queue_index>/finished/', views.finished_jobs, name='rq_finished_jobs'),
    path('queues/<int:queue_index>/failed/', views.failed_jobs, name='rq_failed_jobs'),
    path('queues/<int:queue_index>/failed/clear/', views.delete_failed_jobs, name='rq_delete_failed_jobs'),
    path('queues/<int:queue_index>/scheduled/', views.scheduled_jobs, name='rq_scheduled_jobs'),
    path('queues/<int:queue_index>/started/', views.started_jobs, name='rq_started_jobs'),
    path('queues/<int:queue_index>/deferred/', views.deferred_jobs, name='rq_deferred_jobs'),
    path('queues/<int:queue_index>/empty/', views.clear_queue, name='rq_clear'),
    path('queues/<int:queue_index>/requeue-all/', views.requeue_all, name='rq_requeue_all'),
    path('queues/<int:queue_index>/<str:job_id>/', views.job_detail, name='rq_job_detail'),
    path('queues/<int:queue_index>/<str:job_id>/delete/', views.delete_job, name='rq_delete_job'),
    path('queues/confirm-action/<int:queue_index>/', views.confirm_action, name='rq_confirm_action'),
    path('queues/actions/<int:queue_index>/', views.actions, name='rq_actions'),
    path('queues/<int:queue_index>/<str:job_id>/requeue/', views.requeue_job_view, name='rq_requeue_job'),
    path('queues/<int:queue_index>/<str:job_id>/enqueue/', views.enqueue_job, name='rq_enqueue_job'),
    path('queues/<int:queue_index>/<str:job_id>/stop/', views.stop_job, name='rq_stop_job'),
    path('schedulers/<int:scheduler_index>/', views.scheduler_jobs, name='rq_scheduler_jobs'),
]
