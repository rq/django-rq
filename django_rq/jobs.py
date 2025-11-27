from typing import Optional, Union, cast

from django.conf import settings
from rq.job import Job
from rq.utils import import_attribute


def get_job_class(job_class: Optional[Union[str, type[Job]]] = None) -> type[Job]:
    """
    Return job class from RQ settings, otherwise return Job.
    If `job_class` is not None, it is used as an override (can be
    python import path as string).
    """
    RQ = getattr(settings, 'RQ', {})

    if not job_class:
        job_class = RQ.get('JOB_CLASS')

    # Ensure we never have None (in case someone explicitly sets JOB_CLASS to None)
    if not job_class:
        job_class = Job

    if isinstance(job_class, str):
        job_class = cast(type[Job], import_attribute(job_class))
    return job_class
