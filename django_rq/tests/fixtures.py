from rq import get_current_job
from rq.job import Job
from rq.worker import Worker

from django_rq.queues import DjangoRQ


class DummyJob(Job):
    pass


class DummyQueue(DjangoRQ):
    """Just Fake class for the following test"""


class DummyWorker(Worker):
    pass


try:
    from rq_scheduler import Scheduler

    class DummyScheduler(Scheduler):
        pass
except ImportError:
    pass


def access_self():
    return get_current_job().id
