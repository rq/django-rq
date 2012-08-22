from rq.decorators import job

from .queues import get_queue


class job(job):
    """
    The same as RQ's job decorator, but it works automatically works out
    the ``connection`` argument from RQ_QUEUES.
    """

    def __init__(self, queue, connection=None, *args, **kwargs):        
        if isinstance(queue, basestring):
            try:
                queue = get_queue(queue)
                if connection is None:
                    connection = queue.connection
            except KeyError:
                pass
        super(job, self).__init__(queue, connection, *args, **kwargs)