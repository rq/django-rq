from django import template
from django.utils import timezone
from django.utils.html import escape


register = template.Library()


@register.filter
def to_localtime(time):
    '''Converts naive datetime to localtime based on settings'''

    utc_time = time.replace(tzinfo=timezone.utc)
    to_zone = timezone.get_default_timezone()
    return utc_time.astimezone(to_zone)


@register.filter
def show_func_name(job):
    '''Shows job.func_name and handles errors during deserialization'''
    try:
        return job.func_name
    except Exception as e:
        return repr(e)


@register.filter
def force_escape(text):
    return escape(text)
