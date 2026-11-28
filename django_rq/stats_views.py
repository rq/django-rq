from secrets import compare_digest

from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from . import settings as django_rq_settings
from .utils import get_cron_schedulers, get_rate_limits, get_scheduler_statistics, get_statistics
from .views import each_context, rate_limit_url

try:
    import prometheus_client

    from .contrib.prometheus import RQCollector
except ImportError:
    prometheus_client = RQCollector = None  # type: ignore[assignment, misc]

registry = None


def is_authorized(request: HttpRequest) -> bool:
    api_token = django_rq_settings.get_api_token()
    auth_header = request.headers.get("Authorization", "")
    token = None

    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    is_staff = getattr(request.user, 'is_staff', False)
    return bool(is_staff or (api_token and token and compare_digest(api_token, token)))


@never_cache
def prometheus_metrics(request):
    if not is_authorized(request):
        return JsonResponse(
            {
                "error": True,
                "description": "Missing bearer token. Set token in headers and configure RQ_API_TOKEN in settings.py",
            },
            status=401,
        )

    global registry

    if not RQCollector or not prometheus_client:  # type: ignore[truthy-function]
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
    # Before the rate limits are read, because maintenance deletes drained rate limit
    # registries and promotes waiting jobs. Reading first would render links to keys this
    # same request goes on to remove, which then 404.
    statistics = get_statistics(run_maintenance_tasks=True)

    rate_limits, rate_limit_total = get_rate_limits()
    # URLs are built here rather than in the template, because a key the URL resolver
    # refuses would make `{% rq_url %}` raise mid-render and take the dashboard down.
    for rate_limit in rate_limits:
        rate_limit['url'] = rate_limit_url(request, rate_limit['queue_index'], rate_limit['key'])

    context_data = {
        **each_context(request),
        **statistics,
        **get_scheduler_statistics(),
        "view_metrics": RQCollector is not None,
        "cron_schedulers": get_cron_schedulers(),
        "rate_limits": rate_limits,
        "rate_limit_total": rate_limit_total,
    }
    return render(request, 'django_rq/stats.html', context_data)


@never_cache
def stats_json(request: HttpRequest, token: str | None = None) -> JsonResponse:
    if not is_authorized(request):
        api_token = django_rq_settings.get_api_token()
        if token and compare_digest(token, api_token):
            return JsonResponse(get_statistics())
        else:
            return JsonResponse(
                {
                    "error": True,
                    "description": "Missing bearer token. Set token in headers and configure RQ_API_TOKEN in settings.py",
                },
                status=401,
            )

    return JsonResponse(get_statistics())
