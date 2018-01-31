from rq.job import Job
from rq.utils import import_attribute

from django.conf import settings
from django.utils import six


def get_job_class(job_class=None):
    """
    Return job class from RQ settings, otherwise return Job.
    If `job_class` is not None, it is used as an override (can be
    python import path as string).
    """
    RQ = getattr(settings, 'RQ', {})

    if job_class is None:
        job_class = RQ.get('JOB_CLASS', Job)

    if isinstance(job_class, six.string_types):
        job_class = import_attribute(job_class)
    return job_class
