# Django-RQ

[![Build Status](https://github.com/rq/django-rq/actions/workflows/test.yml/badge.svg)](https://github.com/rq/django-rq/actions/workflows/test.yml)

Django integration with [RQ](https://github.com/nvie/rq), a [Redis](http://redis.io/) based Python queuing library. [Django-RQ](https://github.com/rq/django-rq) is a simple app that allows you to configure your queues in Django's `settings.py` and easily use them in your project.

## Support Django-RQ

If you find `django-rq` useful, please consider supporting its development via [Tidelift](https://tidelift.com/subscription/pkg/pypi-django_rq?utm_source=pypi-django-rq&utm_medium=referral&utm_campaign=readme).

## Requirements

- [Django](https://www.djangoproject.com/) (3.2+)
- [RQ](https://github.com/nvie/rq)

## Installation

- Install `django-rq` (or [download from PyPI](http://pypi.python.org/pypi/django-rq)):

```bash
pip install django-rq
```

- Add `django_rq` to `INSTALLED_APPS` in `settings.py`:

```python
INSTALLED_APPS = (
    # other apps
    "django_rq",
)
```

- Configure your queues in Django's `settings.py`:

```python
RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
        'USERNAME': 'some-user',
        'PASSWORD': 'some-password',
        'DEFAULT_TIMEOUT': 360,
        'DEFAULT_RESULT_TTL': 800,
        'REDIS_CLIENT_KWARGS': {    # Eventual additional Redis connection arguments
            'ssl_cert_reqs': None,
        },
    },
    'with-sentinel': {
        'SENTINELS': [('localhost', 26736), ('localhost', 26737)],
        'MASTER_NAME': 'redismaster',
        'DB': 0,
        # Redis username/password
        'USERNAME': 'redis-user',
        'PASSWORD': 'secret',
        'SOCKET_TIMEOUT': 0.3,
        'CONNECTION_KWARGS': {  # Eventual additional Redis connection arguments
            'ssl': True
        },
        'SENTINEL_KWARGS': {    # Eventual Sentinel connection arguments
            # If Sentinel also has auth, username/password can be passed here
            'username': 'sentinel-user',
            'password': 'secret',
        },
    },
    'high': {
        'URL': os.getenv('REDISTOGO_URL', 'redis://localhost:6379/0'),  # If you're on Heroku
        'DEFAULT_TIMEOUT': 500,
    },
    'low': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
    }
}

RQ_EXCEPTION_HANDLERS = ['path.to.my.handler']  # If you need custom exception handlers
```

## Admin Integration

_Changed in Version 3.0_
Django-RQ automatically integrates with Django's admin interface. Once installed, navigate to `/admin/django_rq/dashboard/` to access:
- Queue statistics and monitoring dashboard
- Job registry browsers (scheduled, started, finished, failed, deferred)
- Worker management
- Prometheus metrics endpoint (if `prometheus_client` is installed)

The views are automatically registered in Django admin and a link to the dashboard is added to the admin interface's sidebar. If you want to disable this link, add `RQ_SHOW_ADMIN_LINK = False` in `settings.py`.

### Standalone URLs (Alternative)

For advanced use cases, you can also include Django-RQ views at a custom URL prefix:

```python
# urls.py
urlpatterns += [
    path('django-rq/', include('django_rq.urls'))
]
```

This makes views accessible at `/django-rq/` instead of within the admin interface at `/admin/django_rq/dashboard/`.

## Usage

### Putting jobs in the queue

Django-RQ allows you to easily put jobs into any of the queues defined in `settings.py`. It comes with a few utility functions:

- `enqueue` - push a job to the `default` queue:

```python
import django_rq
django_rq.enqueue(func, foo, bar=baz)
```

- `get_queue` - returns a `Queue` instance.

```python
import django_rq
queue = django_rq.get_queue('high')
queue.enqueue(func, foo, bar=baz)
```

In addition to `name` argument, `get_queue` also accepts `default_timeout`, `is_async`, `commit_mode`, `connection` and `queue_class` arguments. For example:

```python
queue = django_rq.get_queue('default', commit_mode='on_db_commit', is_async=True, default_timeout=360)
queue.enqueue(func, foo, bar=baz)
```

You can provide your own singleton Redis connection object to this function so that it will not create a new connection object for each queue definition. This will help you limit number of connections to Redis server. For example:

```python
import django_rq
import redis

redis_cursor = redis.StrictRedis(host='', port='', db='', password='')
high_queue = django_rq.get_queue('high', connection=redis_cursor)
low_queue = django_rq.get_queue('low', connection=redis_cursor)
```

- `get_connection` - accepts a single queue name argument (defaults to "default") and returns a connection to the queue's Redis server:

```python
import django_rq

redis_conn = django_rq.get_connection('high')
```

- `get_worker` - accepts optional queue names and returns a new RQ `Worker` instance for specified queues (or `default` queue):

```python
import django_rq

worker = django_rq.get_worker()  # Returns a worker for "default" queue
worker.work()
worker = django_rq.get_worker('low', 'high')  # Returns a worker for "low" and "high"
```

### `@job` decorator

To easily turn a callable into an RQ task, you can also use the `@job` decorator that comes with `django_rq`:

```python
from django_rq import job

@job
def long_running_func():
    pass

long_running_func.delay()  # Enqueue function in "default" queue

@job('high')
def long_running_func():
    pass

long_running_func.delay()  # Enqueue function in "high" queue
```

You can pass in any arguments that RQ's job decorator accepts:

```python
@job('default', timeout=3600)
def long_running_func():
    pass

long_running_func.delay()  # Enqueue function with a timeout of 3600 seconds.
```

It's possible to specify default for `result_ttl` decorator keyword argument via `DEFAULT_RESULT_TTL` setting:

```python
RQ = {
    'DEFAULT_RESULT_TTL': 5000,
}
```

With this setting, job decorator will set `result_ttl` to 5000 unless it's specified explicitly or included in the queue config.

### Running workers

django_rq provides a management command that starts a worker for every queue specified as arguments:

```bash
python manage.py rqworker high default low
```

If you want to run `rqworker` in burst mode, you can pass in the `--burst` flag:

```bash
python manage.py rqworker high default low --burst
```

If you need to use custom worker, job or queue classes, it is best to use global settings (see [Custom queue classes](#custom-queue-classes) and [Custom job and worker classes](#custom-job-and-worker-classes)). However, it is also possible to override such settings with command line options as follows.

To use a custom worker class, you can pass in the `--worker-class` flag with the path to your worker:

```bash
python manage.py rqworker high default low --worker-class 'path.to.GeventWorker'
```

To use a custom queue class, you can pass in the `--queue-class` flag with the path to your queue class:

```bash
python manage.py rqworker high default low --queue-class 'path.to.CustomQueue'
```

To use a custom job class, provide the `--job-class` flag.

Starting from version 2.10, running RQ's worker-pool is also supported:

```bash
python manage.py rqworker-pool default low medium --num-workers 4
```

### Support for Scheduled Jobs

With RQ 1.2.0 you can use the [built-in scheduler](https://python-rq.org/docs/scheduling/) for your jobs. For example:

```python
from datetime import datetime
from django_rq.queues import get_queue

queue = get_queue('default')
job = queue.enqueue_at(datetime(2020, 10, 10), func)
```

If you are using built-in scheduler you have to start workers with scheduler support:

```bash
python manage.py rqworker --with-scheduler
```

### Support for RQ's CronScheduler

Create a cron configuration file:

```python
# cron_config.py
from rq import cron
from myapp.tasks import send_report, sync_data

cron.register(send_report, queue_name='default', cron='0 9 * * *')  # Daily at 9:00 AM
cron.register(sync_data, queue_name='high', interval=30)  # Every 30 seconds
```

Then start the cron scheduler:

```bash
python manage.py rqcron cron_config.py
```

For more options, visit [RQ's CronScheduler documentation](https://python-rq.org/docs/cron/).

### Support for django-redis and django-redis-cache

If you have [django-redis](https://django-redis.readthedocs.org/) or [django-redis-cache](https://github.com/sebleier/django-redis-cache/) installed, you can instruct django_rq to use the same connection information from your Redis cache. This has two advantages: it's DRY and it takes advantage of any optimization that may be going on in your cache setup (like using connection pooling or [Hiredis](https://github.com/redis/hiredis)).

To configure it, use a dict with the key `USE_REDIS_CACHE` pointing to the name of the desired cache in your `RQ_QUEUES` dict. It goes without saying that the chosen cache must exist and use the Redis backend. See your respective Redis cache package docs for configuration instructions. It's also important to point out that since the django-redis-cache `ShardedClient` splits the cache over multiple Redis connections, it does not work.

Here is an example settings fragment for `django-redis`:

```python
CACHES = {
    'redis-cache': {
        'BACKEND': 'redis_cache.cache.RedisCache',
        'LOCATION': 'localhost:6379:1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_ENTRIES': 5000,
        },
    },
}

RQ_QUEUES = {
    'high': {
        'USE_REDIS_CACHE': 'redis-cache',
    },
    'low': {
        'USE_REDIS_CACHE': 'redis-cache',
    },
}
```

### Suspending and Resuming Workers

Sometimes you may want to suspend RQ to prevent it from processing new jobs. A classic example is during the initial phase of a deployment script or in advance of putting your site into maintenance mode. This is particularly helpful when you have jobs that are relatively long-running and might otherwise be forcibly killed during the deploy.

The `suspend` command stops workers on _all_ queues (in a single Redis database) from picking up new jobs. However currently running jobs will continue until completion.

```bash
# Suspend indefinitely
python manage.py rqsuspend

# Suspend for a specific duration (in seconds) then automatically
# resume work again.
python manage.py rqsuspend -d 600

# Resume work again.
python manage.py rqresume
```

### Queue Statistics

_Changed in Version 3.0_

Various queue statistics are also available in JSON format via `/django-rq/stats.json`, which is accessible via a bearer token authentication scheme (defined in `settings.py` as `RQ_API_TOKEN`). Then, include the token in the Authorization header as a Bearer token: `Authorization: Bearer <token>` and access it via `/django-rq/stats.json`.

![Django RQ JSON dashboard](demo-django-rq-json-dashboard.png)

Note: Statistics of scheduled jobs display jobs from [RQ built-in scheduler](https://python-rq.org/docs/scheduling/), not optional [RQ scheduler](https://github.com/rq/rq-scheduler).

Additionally, these statistics are also accessible from the command line.

```bash
python manage.py rqstats
python manage.py rqstats --interval=1  # Refreshes every second
python manage.py rqstats --json  # Output as JSON
python manage.py rqstats --yaml  # Output as YAML
```

![Django RQ CLI dashboard](demo-django-rq-cli-dashboard.gif)

### Configuring Prometheus

`django_rq` also provides a Prometheus compatible view, which can be enabled by installing `prometheus_client` or installing the extra "prometheus-metrics" (`pip install django-rq[prometheus]`). The metrics are exposed at `/django-rq/metrics/` and the following is an example of the metrics that are exported:

```text
# HELP rq_workers RQ workers
# TYPE rq_workers gauge
# HELP rq_job_successful_total RQ successful job count
# TYPE rq_job_successful_total counter
# HELP rq_job_failed_total RQ failed job count
# TYPE rq_job_failed_total counter
# HELP rq_working_seconds_total RQ total working time
# TYPE rq_working_seconds_total counter
# HELP rq_jobs RQ jobs by status
# TYPE rq_jobs gauge
rq_jobs{queue="default",status="queued"} 0.0
rq_jobs{queue="default",status="started"} 0.0
rq_jobs{queue="default",status="finished"} 0.0
rq_jobs{queue="default",status="failed"} 0.0
rq_jobs{queue="default",status="deferred"} 0.0
rq_jobs{queue="default",status="scheduled"} 0.0
```

If you need to access this view via other HTTP clients (for monitoring purposes), you can define `RQ_API_TOKEN`. Then, include the token in the Authorization header as a Bearer token: `Authorization: Bearer <token>` and access it via `/django-rq/metrics`.


### Configuring Logging

RQ uses Python's `logging`, this means you can easily configure `rqworker`'s logging mechanism in Django's `settings.py`. For example:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "rq_console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "rq_console": {
            "level": "DEBUG",
            "class": "rq.logutils.ColorizingStreamHandler",
            "formatter": "rq_console",
            "exclude": ["%(asctime)s"],
        },
    },
    'loggers': {
        "rq.worker": {
            "handlers": ["rq_console", "sentry"],
            "level": "DEBUG"
        },
    }
}
```

### Custom Queue Classes

By default, every queue will use `DjangoRQ` class. If you want to use a custom queue class, you can do so by adding a `QUEUE_CLASS` option on a per queue basis in `RQ_QUEUES`:

```python
RQ_QUEUES = {
    'default': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
        'QUEUE_CLASS': 'module.path.CustomClass',
    }
}
```

Or you can specify `DjangoRQ` to use a custom class for all your queues in `RQ` settings:

```python
RQ = {
    'QUEUE_CLASS': 'module.path.CustomClass',
}
```

Custom queue classes should inherit from `django_rq.queues.DjangoRQ`.

If you are using more than one queue class (not recommended), be sure to only run workers on queues with same queue class. For example if you have two queues defined in `RQ_QUEUES` and one has custom class specified, you would have to run at least two separate workers for each queue.

### Custom Job and Worker Classes

Similarly to custom queue classes, global custom job and worker classes can be configured using `JOB_CLASS` and `WORKER_CLASS` settings:

```python
RQ = {
    'JOB_CLASS': 'module.path.CustomJobClass',
    'WORKER_CLASS': 'module.path.CustomWorkerClass',
}
```

Custom job class should inherit from `rq.job.Job`. It will be used for all jobs if configured.

Custom worker class should inherit from `rq.worker.Worker`. It will be used for running all workers unless overridden by `rqworker` management command `worker-class` option.

### Testing Tip

For an easier testing process, you can run a worker synchronously this way:

```python
from django.test import TestCase
from django_rq import get_worker

class MyTest(TestCase):
    def test_something_that_creates_jobs(self):
        ...                      # Stuff that init jobs.
        get_worker().work(burst=True)  # Processes all jobs then stop.
        ...                      # Asserts that the job stuff is done.
```

### Synchronous Mode

You can set the option `ASYNC` to `False` to make synchronous operation the default for a given queue. This will cause jobs to execute immediately and on the same thread as they are dispatched, which is useful for testing and debugging. For example, you might add the following after your queue configuration in your settings file:

```python
# ... Logic to set DEBUG and TESTING settings to True or False ...

# ... Regular RQ_QUEUES setup code ...

if DEBUG or TESTING:
    for queue_config in RQ_QUEUES.values():
        queue_config['ASYNC'] = False
```

Note that setting the `is_async` parameter explicitly when calling `get_queue` will override this setting.

### Commit Modes

*New in version 3.0 (not yet released)*

By default, jobs are enqueued when the database transaction commits. This behavior is controlled by the `COMMIT_MODE` setting:

```python
RQ = {
    'COMMIT_MODE': 'on_db_commit',  # or 'auto', 'request_finished'
}
```

Available commit modes:

| Mode | Behavior |
|------|----------|
| `on_db_commit` (default) | Jobs are enqueued when the current database transaction commits. If not in a transaction, jobs are enqueued immediately |
| `auto` | Jobs are enqueued immediately when `enqueue()` is called |
| `request_finished` | Jobs are enqueued when Django's `request_finished` signal fires. Jobs are discarded if an exception occurs during the request |

The `on_db_commit` mode is recommended when your jobs depend on database state, as it ensures the job won't run until the data it depends on has been committed. This prevents race conditions where a job tries to access data that hasn't been committed.

```python
from django.db import transaction

# With COMMIT_MODE='on_db_commit'
with transaction.atomic():
    user = User.objects.create(username='new_user')
    queue.enqueue(send_welcome_email, user.id) # Job not enqueued yet, it waits for DB transaction to commit
    
# Transaction committed - now the job is enqueued
```

You can also explicitly set `commit_mode` when calling `get_queue()`:

```python
queue = django_rq.get_queue('default', commit_mode='auto')
```

**Note:** The `AUTOCOMMIT` setting is deprecated as of version 3.0. Use `COMMIT_MODE` instead:
- `AUTOCOMMIT: True` → `COMMIT_MODE: 'auto'`
- `AUTOCOMMIT: False` → `COMMIT_MODE: 'request_finished'`

**Migrating from version 2.x:** The default behavior has changed in version 3.0. Previously, jobs were enqueued immediately (`auto` mode). Now, jobs are enqueued when the database transaction commits (`on_db_commit` mode). To restore the old behavior, set `COMMIT_MODE: 'auto'` in your `RQ` settings.

## Running Tests

To run `django_rq`'s test suite (you'll need `pytest-django`):

```bash
pytest
```

## Deploying on Ubuntu

Create an rqworker service that runs the high, default, and low queues.

```bash
sudo vi /etc/systemd/system/rqworker.service
```

```bash
[Unit]
Description=Django-RQ Worker
After=network.target

[Service]
WorkingDirectory=<<path_to_your_project_folder>>
ExecStart=/home/ubuntu/.virtualenv/<<your_virtualenv>>/bin/python \
    <<path_to_your_project_folder>>/manage.py \
    rqworker high default low

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable rqworker
sudo systemctl start rqworker
```

## Deploying on Heroku

Add `django-rq` to your `requirements.txt` file with:

```bash
pip freeze > requirements.txt
```

Update your `Procfile` to:

```bash
web: gunicorn --pythonpath="$PWD/your_app_name" config.wsgi:application

worker: python your_app_name/manage.py rqworker high default low
```

Commit and re-deploy. Then add your new worker with:

```bash
heroku scale worker=1
```

## Changelog

See [CHANGELOG.md](https://github.com/rq/django-rq/blob/master/CHANGELOG.md).

---

Django-RQ is maintained by [Stamps](https://stamps.id), an Indonesian based company that provides enterprise grade CRM and order management systems.
