from dateutil import tz

from django import template
from django.conf import settings


register = template.Library()


@register.filter
def to_localtime(time):
    '''
        A function to convert naive datetime to
        localtime base on settings
    '''
    utc_zone = tz.tzutc()
    utc_time = time.replace(tzinfo=utc_zone)
    to_zone = tz.gettz(settings.TIME_ZONE)
    return utc_time.astimezone(to_zone)
