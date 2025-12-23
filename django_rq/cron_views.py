from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .connection_utils import get_connection_by_index
from .cron import DjangoCronScheduler
from .views import each_context


@never_cache
@staff_member_required
def cron_scheduler_detail(request, connection_index: int, scheduler_name: str):
    """
    Display details for a specific cron scheduler.

    Args:
        request: Django request object
        connection_index: Index of the Redis connection
        scheduler_name: Name of the cron scheduler

    Raises:
        Http404: If the scheduler is not found
    """
    try:
        connection = get_connection_by_index(connection_index)
        schedulers = DjangoCronScheduler.all(connection, cleanup=True)

        # Find the scheduler with the matching name
        scheduler = None
        for s in schedulers:
            if s.name == scheduler_name:
                scheduler = s
                break

        if scheduler is None:
            raise Http404(f"Scheduler '{scheduler_name}' not found")

        context_data = {
            **each_context(request),
            "scheduler": scheduler,
        }

        return render(request, 'django_rq/cron_scheduler_detail.html', context_data)

    except (IndexError, ValueError):
        raise Http404("Invalid connection index")
