import django
from multiprocessing import Process, get_start_method
from typing import Any

from rq.worker_pool import WorkerPool, run_worker


class DjangoWorkerPool(WorkerPool):
    def get_worker_process(
        self,
        name: str,
        burst: bool,
        _sleep: float = 0,
        logging_level: str = "INFO",
    ) -> Process:
        """Returns the worker process"""
        return Process(
            target=run_django_worker,
            args=(name, self._queue_names, self._connection_class, self._pool_class, self._pool_kwargs),
            kwargs={
                '_sleep': _sleep,
                'burst': burst,
                'logging_level': logging_level,
                'worker_class': self.worker_class,
                'job_class': self.job_class,
                'serializer': self.serializer,
            },
            name=f'Worker {name} (WorkerPool {self.name})',
        )


def run_django_worker(*args: Any, **kwargs: Any) -> None:
    # multiprocessing library default process start method may be
    # `spawn` or `fork` depending on the host OS
    if get_start_method() == 'spawn':
        django.setup()

    run_worker(*args, **kwargs)
