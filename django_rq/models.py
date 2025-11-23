from django.core.signals import got_request_exception, request_finished
from django.db import models

from . import thread_queue
from .queues import get_commit_mode

# Wire up request finished/exception signal only for the request_finished mode
if get_commit_mode() == 'request_finished':
    request_finished.connect(thread_queue.commit)
    got_request_exception.connect(thread_queue.clear)


class Queue(models.Model):
    """Placeholder model with no database table, but with django admin page
    and contenttype permission"""

    class Meta:
        managed = False  # not in Django's database
        default_permissions = ()
        permissions = [['view', 'Access admin page']]
