from django import template
from django.utils import timezone


register = template.Library()


@register.filter
def to_localtime(time):
    '''
        A function to convert naive datetime to
        localtime base on settings
    '''

    if not time:
        return None
    
    utc_time = time.replace(tzinfo=timezone.utc)
    to_zone = timezone.get_default_timezone()
    return utc_time.astimezone(to_zone)
