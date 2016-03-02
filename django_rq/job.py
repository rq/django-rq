try:
    from pytz import timezone
    from django.utils.timezone import make_aware
except ImportError:
    pass

from rq.job import Job

TIMEZONE_AWARE_FIELDS = (
    'created_at',
    'enqueued_at',
    'started_at',
    'ended_at',
)

class TZAwareJob(Job):
    def __getattribute__(self, name):
        attr = super(TZAwareJob, self).__getattribute__(name)
        if name in TIMEZONE_AWARE_FIELDS and attr is not None:
            try:
                return make_aware(attr, timezone('UTC'))
            except NameError:
                return attr
        return attr


