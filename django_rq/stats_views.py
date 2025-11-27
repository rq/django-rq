from secrets import compare_digest

from typing import Optional

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .settings import API_TOKEN
from .utils import get_cron_schedulers, get_scheduler_statistics, get_statistics

try:
    import prometheus_client

    from .contrib.prometheus import RQCollector
except ImportError:
    prometheus_client = RQCollector = None  # type: ignore[assignment, misc]

registry = None


def is_authorized(request: HttpRequest) -> bool:
    auth_header = request.headers.get("Authorization", "")
    token = None

    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    is_staff = getattr(request.user, 'is_staff', False)
    return bool(is_staff or (API_TOKEN and token and compare_digest(API_TOKEN, token)))


@never_cache
def prometheus_metrics(request):
    if not is_authorized(request):
        return JsonResponse(
            {
                "error": True,
                "description": "Missing bearer token. Set token in headers and configure RQ_API_TOKEN in settings.py",
            }
        )

    global registry

    if not RQCollector:  # type: ignore[truthy-function]
        raise Http404('prometheus_client has not been installed; install using extra "django-rq[prometheus]"')

    if not registry:
        registry = prometheus_client.CollectorRegistry(auto_describe=True)
        registry.register(RQCollector())

    encoder, content_type = prometheus_client.exposition.choose_encoder(request.META.get('HTTP_ACCEPT', ''))
    if 'name[]' in request.GET:
        registry = registry.restricted_registry(request.GET.getlist('name[]'))

    return HttpResponse(encoder(registry), headers={'Content-Type': content_type})


@never_cache
@staff_member_required
def stats(request: HttpRequest) -> HttpResponse:
    context_data = {
        **admin.site.each_context(request),
        **get_statistics(run_maintenance_tasks=True),
        **get_scheduler_statistics(),
        "view_metrics": RQCollector is not None,
        "cron_schedulers": get_cron_schedulers(),
    }
    return render(request, 'django_rq/stats.html', context_data)


@never_cache
def stats_json(request: HttpRequest, token: Optional[str] = None) -> JsonResponse:
    if not is_authorized(request):
        if token and token == API_TOKEN:
            return JsonResponse(get_statistics())
        else:
            return JsonResponse(
                {
                    "error": True,
                    "description": "Missing bearer token. Set token in headers and configure RQ_API_TOKEN in settings.py",
                }
            )

    return JsonResponse(get_statistics())
