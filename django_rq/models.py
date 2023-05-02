from django.core.signals import got_request_exception, request_finished
from django.db import models

from . import thread_queue
from .queues import get_commit_mode

# If we're not in AUTOCOMMIT mode, wire up request finished/exception signal
if not get_commit_mode():
    request_finished.connect(thread_queue.commit)
    got_request_exception.connect(thread_queue.clear)


class Queue(models.Model):
    """Placeholder model with no database table, but with django admin page
    and contenttype permission"""
    class Meta:
        managed = False  # not in Django's database
        default_permissions = ()
        permissions = [['view', 'Access admin page']]
