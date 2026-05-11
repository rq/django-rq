import datetime

from django import template
from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from rq.exceptions import InvalidJobOperation

register = template.Library()


@register.filter
def to_localtime(time):
    """Converts naive datetime to localtime based on settings"""

    utc_time = time.replace(tzinfo=datetime.timezone.utc)
    to_zone = timezone.get_default_timezone()
    return utc_time.astimezone(to_zone)


@register.filter
def timestamp_tooltip(timestamp):
    """Render a datetime in the configured TIME_ZONE, with the raw UTC
    value exposed via a hover tooltip. Empty input renders as an em-dash.

    Naive datetimes are treated as UTC (RQ's storage convention).
    Aware datetimes are converted to UTC via ``astimezone`` to avoid the
    silent misinterpretation that ``replace(tzinfo=…)`` would cause on
    already-aware values.
    """
    if not timestamp:
        return mark_safe("—")
    if timezone.is_naive(timestamp):
        utc = timestamp.replace(tzinfo=datetime.timezone.utc)
    else:
        utc = timestamp.astimezone(datetime.timezone.utc)
    local = utc.astimezone(timezone.get_default_timezone())
    fmt = "Y-m-d H:i:s"
    utc_str = dateformat.format(utc, fmt)
    local_str = dateformat.format(local, fmt)
    return mark_safe(
        f'<time datetime="{escape(utc.isoformat())}" '
        f'title="UTC: {escape(utc_str)}">{escape(local_str)}</time>'
    )


@register.filter
def show_func_name(job):
    """Shows job.func_name and handles errors during deserialization"""
    try:
        return job.func_name
    except Exception as e:
        return repr(e)


@register.filter
def job_status(job):
    """Shows job status and handles stale scheduler/job registry entries."""
    try:
        status = job.get_status()
    except InvalidJobOperation:
        return 'unknown'
    return getattr(status, 'value', status)


@register.filter
def force_escape(text):
    return escape(text)


@register.filter
def items(dictionary):
    """
    Explicitly calls `dictionary.items` function
    to avoid django from accessing the key `items` if any.
    """
    return dictionary.items()


@register.simple_tag(takes_context=True)
def rq_url(context, viewname, *args, **kwargs):
    """
    Reverse django-rq URLs for both admin integration and standalone URLs.

    The django-rq views live under different namespaces depending on how they
    are wired: admin integration uses the admin site's namespace (e.g.
    "admin:django_rq_*"), while standalone URLs use the "django_rq:" namespace.
    This tag detects the current admin namespace from request.current_app and
    builds the correct namespaced view name.
    """
    request = context.get("request")
    current_app = getattr(request, "current_app", None) if request else None
    if current_app:
        prefix = f"{current_app}:django_rq_"
    else:
        prefix = "django_rq:"
    return reverse(f"{prefix}{viewname}", args=args, kwargs=kwargs)
