from typing import Callable, Optional

from django.urls import URLPattern, path, re_path

from . import cron_views, stats_views, views
from .contrib.prometheus import RQCollector


def get_api_urlpatterns(name_prefix: str = '') -> list[URLPattern]:
    """
    Get URL patterns for views that have their own authentication (API tokens).

    These views should NOT be wrapped with admin_view because they support
    API token authentication that must work without Django session auth.

    Returns:
        List of URL patterns for API-authenticated views.
    """
    # Conditional metrics view (only if prometheus_client is installed)
    metrics_view = (
        [
            re_path(r'^metrics/?$', stats_views.prometheus_metrics, name=f'{name_prefix}metrics'),
        ]
        if RQCollector is not None
        else []
    )

    return [
        # Stats JSON (supports API token authentication)
        re_path(r'^stats.json/?$', stats_views.stats_json, name=f'{name_prefix}home_json'),
        re_path(r'^stats.json/(?P<token>[\w]+)?/?$', stats_views.stats_json, name=f'{name_prefix}home_json'),
        # Prometheus metrics (supports API token authentication)
        *metrics_view,
    ]


def get_admin_urlpatterns(name_prefix: str = '', view_wrapper: Optional[Callable] = None) -> list[URLPattern]:
    """
    Get URL patterns for views that should be wrapped with admin authentication.

    Args:
        view_wrapper: Optional function to wrap each view (e.g., admin_site.admin_view).

    Returns:
        List of URL patterns for admin-authenticated views.
    """

    def maybe_wrap(view: Callable) -> Callable:
        """Apply wrapper if provided, otherwise return view as-is"""
        return view_wrapper(view) if view_wrapper else view

    return [
        # Dashboard
        path('', maybe_wrap(stats_views.stats), name=f'{name_prefix}home'),
        # Queue views
        path('queues/<int:queue_index>/', maybe_wrap(views.jobs), name=f'{name_prefix}jobs'),
        path('queues/<int:queue_index>/finished/', maybe_wrap(views.finished_jobs), name=f'{name_prefix}finished_jobs'),
        path('queues/<int:queue_index>/failed/', maybe_wrap(views.failed_jobs), name=f'{name_prefix}failed_jobs'),
        path('queues/<int:queue_index>/failed/clear/', maybe_wrap(views.delete_failed_jobs), name=f'{name_prefix}delete_failed_jobs'),
        path('queues/<int:queue_index>/scheduled/', maybe_wrap(views.scheduled_jobs), name=f'{name_prefix}scheduled_jobs'),
        path('queues/<int:queue_index>/started/', maybe_wrap(views.started_jobs), name=f'{name_prefix}started_jobs'),
        path('queues/<int:queue_index>/deferred/', maybe_wrap(views.deferred_jobs), name=f'{name_prefix}deferred_jobs'),
        path('queues/<int:queue_index>/empty/', maybe_wrap(views.clear_queue), name=f'{name_prefix}clear'),
        path('queues/<int:queue_index>/requeue-all/', maybe_wrap(views.requeue_all), name=f'{name_prefix}requeue_all'),
        # Job detail and actions
        path('queues/<int:queue_index>/<str:job_id>/', maybe_wrap(views.job_detail), name=f'{name_prefix}job_detail'),
        path('queues/<int:queue_index>/<str:job_id>/delete/', maybe_wrap(views.delete_job), name=f'{name_prefix}delete_job'),
        path('queues/<int:queue_index>/<str:job_id>/requeue/', maybe_wrap(views.requeue_job_view), name=f'{name_prefix}requeue_job'),
        path('queues/<int:queue_index>/<str:job_id>/enqueue/', maybe_wrap(views.enqueue_job), name=f'{name_prefix}enqueue_job'),
        path('queues/<int:queue_index>/<str:job_id>/stop/', maybe_wrap(views.stop_job), name=f'{name_prefix}stop_job'),
        # Bulk actions
        path('queues/confirm-action/<int:queue_index>/', maybe_wrap(views.confirm_action), name=f'{name_prefix}confirm_action'),
        path('queues/actions/<int:queue_index>/', maybe_wrap(views.actions), name=f'{name_prefix}actions'),
        # Workers
        path('workers/<int:queue_index>/', maybe_wrap(views.workers), name=f'{name_prefix}workers'),
        path('workers/<int:queue_index>/<str:key>/', maybe_wrap(views.worker_details), name=f'{name_prefix}worker_details'),
        # Schedulers
        path('schedulers/<int:scheduler_index>/', maybe_wrap(views.scheduler_jobs), name=f'{name_prefix}scheduler_jobs'),
        path(
            'cron-schedulers/<int:connection_index>/<str:scheduler_name>/',
            maybe_wrap(cron_views.cron_scheduler_detail),
            name=f'{name_prefix}cron_scheduler_detail',
        ),
    ]


# Standalone URL patterns (for use with include('django_rq.urls'))
# Combines both API and admin patterns without wrapping
app_name = "django_rq"
urlpatterns = get_api_urlpatterns() + get_admin_urlpatterns()
