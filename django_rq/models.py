from django.core.signals import got_request_exception, request_finished
from django.db import models

from . import thread_queue
from .queues import get_commit_mode

# Wire up request finished/exception signal only for the request_finished mode
if get_commit_mode() == 'request_finished':
    request_finished.connect(thread_queue.commit)
    got_request_exception.connect(thread_queue.clear)


class Queue(models.Model):
    """
    Admin-only model for Django-RQ dashboard integration.
    """

    class Meta:
        managed = False  # No database table - admin integration only
        default_permissions = ()
        permissions = [['view', 'Access admin page']]
        verbose_name = 'Django-RQ'
        verbose_name_plural = 'Django-RQ'
