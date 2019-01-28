=========
Django-RQ
=========

|Build Status|

Django integration with `RQ <https://github.com/nvie/rq>`__, a `Redis <http://redis.io/>`__
based Python queuing library. `Django-RQ <https://github.com/rq/django-rq>`__ is a
simple app that allows you to configure your queues in django's ``settings.py``
and easily use them in your project.

============
Requirements
============

* `Django <https://www.djangoproject.com/>`__ (1.8+)
* `RQ <https://github.com/nvie/rq>`__

============
Installation
============

* Install ``django-rq`` (or `download from PyPI <http://pypi.python.org/pypi/django-rq>`__):

.. code-block:: python

    pip install django-rq

* Add ``django_rq`` to ``INSTALLED_APPS`` in ``settings.py``:

.. code-block:: python

    INSTALLED_APPS = (
        # other apps
        "django_rq",
    )

* Configure your queues in django's ``settings.py`` (syntax based on Django's database config):

.. code-block:: python

    RQ_QUEUES = {
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'PASSWORD': 'some-password',
            'DEFAULT_TIMEOUT': 360,
        },
        'with-sentinel': {
            'SENTINELS': [('localhost', 26736), ('localhost', 26737)],
            'MASTER_NAME': 'redismaster',
            'DB': 0,
            'PASSWORD': 'secret',
            'SOCKET_TIMEOUT': None,
            'CONNECTION_KWARGS': {
                'socket_connect_timeout': 0.3
            },
        },
        'high': {
            'URL': os.getenv('REDISTOGO_URL', 'redis://localhost:6379/0'), # If you're on Heroku
            'DEFAULT_TIMEOUT': 500,
        },
        'low': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
    }

    RQ_EXCEPTION_HANDLERS = ['path.to.my.handler'] # If you need custom exception handlers

* Include ``django_rq.urls`` in your ``urls.py``:

.. code-block:: python

    # For Django < 2.0
    urlpatterns += [
        url(r'^django-rq/', include('django_rq.urls')),
    ]

    # For Django >= 2.0
    urlpatterns += [
        path('django-rq/', include('django_rq.urls'))
    ]

=====
Usage
=====

Putting jobs in the queue
-------------------------

`Django-RQ` allows you to easily put jobs into any of the queues defined in
``settings.py``. It comes with a few utility functions:

* ``enqueue`` - push a job to the ``default`` queue:

.. code-block:: python

    import django_rq
    django_rq.enqueue(func, foo, bar=baz)

* ``get_queue`` - returns an ``Queue`` instance.

.. code-block:: python

    import django_rq
    queue = django_rq.get_queue('high')
    queue.enqueue(func, foo, bar=baz)

In addition to ``name`` argument, ``get_queue`` also accepts ``default_timeout``,
``is_async``, ``autocommit``, ``connection`` and ``queue_class`` arguments. For example:

.. code-block:: python

    queue = django_rq.get_queue('default', autocommit=True, is_async=True, default_timeout=360)
    queue.enqueue(func, foo, bar=baz)

You can provide your own singleton Redis connection object to this function so that it will not
create a new connection object for each queue definition. This will help you limit
number of connections to Redis server. For example:

.. code-block:: python

    import django_rq
    import redis
    redis_cursor = redis.StrictRedis(host='', port='', db='', password='')
    high_queue = django_rq.get('high', connection=redis_cursor)
    low_queue = django_rq.get('low', connection=redis_cursor)


* ``get_connection`` - accepts a single queue name argument (defaults to "default")
  and returns a connection to the queue's `Redis`_ server:

.. code-block:: python

    import django_rq
    redis_conn = django_rq.get_connection('high')

* ``get_worker`` - accepts optional queue names and returns a new `RQ`
  ``Worker`` instance for specified queues (or ``default`` queue):

.. code-block:: python

    import django_rq
    worker = django_rq.get_worker() # Returns a worker for "default" queue
    worker.work()
    worker = django_rq.get_worker('low', 'high') # Returns a worker for "low" and "high"


@job decorator
--------------

To easily turn a callable into an RQ task, you can also use the ``@job``
decorator that comes with ``django_rq``:

.. code-block:: python

    from django_rq import job

    @job
    def long_running_func():
        pass
    long_running_func.delay() # Enqueue function in "default" queue

    @job('high')
    def long_running_func():
        pass
    long_running_func.delay() # Enqueue function in "high" queue

It's possible to specify default for ``result_ttl`` decorator keyword argument
via ``DEFAULT_RESULT_TTL`` setting:

.. code-block:: python

    RQ = {
        'DEFAULT_RESULT_TTL': 5000,
    }

With this setting, job decorator will set ``result_ttl`` to 5000 unless it's
specified explicitly.


Running workers
---------------
django_rq provides a management command that starts a worker for every queue
specified as arguments::

    python manage.py rqworker high default low

If you want to run ``rqworker`` in burst mode, you can pass in the ``--burst`` flag::

    python manage.py rqworker high default low --burst

If you need to use custom worker, job or queue classes, it is best to use global settings
(see `Custom queue classes`_ and `Custom job and worker classes`_). However, it is also possible
to override such settings with command line options as follows.

To use a custom worker class, you can pass in the ``--worker-class`` flag
with the path to your worker::

    python manage.py rqworker high default low --worker-class 'path.to.GeventWorker'

To use a custom queue class, you can pass in the ``--queue-class`` flag
with the path to your queue class::

    python manage.py rqworker high default low --queue-class 'path.to.CustomQueue'

To use a custom job class, provide ``--job-class`` flag.

Support for RQ Scheduler
------------------------

If you have `RQ Scheduler <https://github.com/ui/rq-scheduler>`__ installed,
you can also use the ``get_scheduler`` function to return a ``Scheduler``
instance for queues defined in settings.py's ``RQ_QUEUES``. For example:

.. code-block:: python

    import django_rq
    scheduler = django_rq.get_scheduler('default')
    job = scheduler.enqueue_at(datetime(2020, 10, 10), func)

You can also use the management command ``rqscheduler`` to start the scheduler::

    python manage.py rqscheduler

Support for django-redis and django-redis-cache
-----------------------------------------------

If you have `django-redis <https://django-redis.readthedocs.org/>`__ or
`django-redis-cache <https://github.com/sebleier/django-redis-cache/>`__
installed, you can instruct django_rq to use the same connection information
from your Redis cache. This has two advantages: it's DRY and it takes advantage
of any optimization that may be going on in your cache setup (like using
connection pooling or `Hiredis <https://github.com/redis/hiredis>`__.)

To use configure it, use a dict with the key ``USE_REDIS_CACHE`` pointing to the
name of the desired cache in your ``RQ_QUEUES`` dict. It goes without saying
that the chosen cache must exist and use the Redis backend. See your respective
Redis cache package docs for configuration instructions. It's also important to
point out that since the django-redis-cache ``ShardedClient`` splits the cache
over multiple Redis connections, it does not work.

Here is an example settings fragment for `django-redis`:

.. code-block:: python

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

Queue Statistics
----------------

``django_rq`` also provides a dashboard to monitor the status of your queues at
``/django-rq/`` (or whatever URL you set in your ``urls.py`` during installation.

You can also add a link to this dashboard link in ``/admin`` by adding
``RQ_SHOW_ADMIN_LINK = True`` in ``settings.py``. Be careful though, this will
override the default admin template so it may interfere with other apps that
modifies the default admin template.

These statistics are also available in JSON format via
``/django-rq/stats.json``, which is accessible to staff members.
If you need to access this view via other
HTTP clients (for monitoring purposes), you can define ``RQ_API_TOKEN`` and access it via
``/django-rq/stats.json/<API_TOKEN>``.

.. image::  demo-django-rq-json-dashboard.png


Additionaly, these statistics are also accessible from  the command line.

.. code-block:: bash

    python manage.py rqstats
    python manage.py rqstats --interval=1  # Refreshes every second
    python manage.py rqstats --json  # Output as JSON
    python manage.py rqstats --yaml  # Output as YAML

.. image:: demo-django-rq-cli-dashboard.gif

Configuring Sentry
-------------------
The ``SENTRY_DSN`` value from ``settings.py`` is used by default:

``SENTRY_DSN = 'https://*****@sentry.io/222222'``

Also you can specify ``sentry-dsn`` parameter when running rqworker:

``./manage.py rqworker --sentry-dsn=https://*****@sentry.io/222222``


**Disable RQ sentry plugin**

If your project use ``sentry-sdk``, the DSN is not compatible with RQ's sentry plugin (based on raven).
In that case you have to disable the sentry plugin by setting `--sentry-dsn=""`.

Configuring Logging
-------------------

Starting from version 0.3.3, RQ uses Python's ``logging``, this means
you can easily configure ``rqworker``'s logging mechanism in django's
``settings.py``. For example:

.. code-block:: python

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
                "class": "rq.utils.ColorizingStreamHandler",
                "formatter": "rq_console",
                "exclude": ["%(asctime)s"],
            },
            # If you use sentry for logging
            'sentry': {
                'level': 'ERROR',
                'class': 'raven.contrib.django.handlers.SentryHandler',
            },
        },
        'loggers': {
            "rq.worker": {
                "handlers": ["rq_console", "sentry"],
                "level": "DEBUG"
            },
        }
    }

Note: error logging to Sentry is known to be unreliable with RQ when using async
transports (the default transport). Please configure ``Raven`` to use
``sync+https://`` or ``requests+https://`` transport in ``settings.py``:

.. code-block:: python

    RAVEN_CONFIG = {
        'dsn': 'sync+https://public:secret@example.com/1',
    }

For more info, refer to `Raven's documentation <http://raven.readthedocs.org/>`__.

Custom Queue Classes
--------------------

By default, every queue will use ``DjangoRQ`` class. If you want to use a custom queue class, you can do so
by adding a ``QUEUE_CLASS`` option on a per queue basis in ``RQ_QUEUES``:

.. code-block:: python

    RQ_QUEUES = {
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'QUEUE_CLASS': 'module.path.CustomClass',
        }
    }

or you can specify ``DjangoRQ`` to use a custom class for all your queues in ``RQ`` settings:

.. code-block:: python

    RQ = {
        'QUEUE_CLASS': 'module.path.CustomClass',
    }

Custom queue classes should inherit from ``django_rq.queues.DjangoRQ``.

If you are using more than one queue class (not recommended), be sure to only run workers
on queues with same queue class. For example if you have two queues defined in ``RQ_QUEUES`` and
one has custom class specified, you would have to run at least two separate workers for each
queue.

Custom Job and Worker Classes
-----------------------------

Similarly to custom queue classes, global custom job and worker classes can be configured using
``JOB_CLASS`` and ``WORKER_CLASS`` settings:

.. code-block:: python

    RQ = {
        'JOB_CLASS': 'module.path.CustomJobClass',
        'WORKER_CLASS': 'module.path.CustomWorkerClass',
    }

Custom job class should inherit from ``rq.job.Job``. It will be used for all jobs
if configured.

Custom worker class should inherit from ``rq.worker.Worker``. It will be used for running
all workers unless overriden by ``rqworker`` management command ``worker-class`` option.

Testing Tip
-----------

For an easier testing process, you can run a worker synchronously this way:

.. code-block:: python

    from django.test import TestCase
    from django_rq import get_worker

    class MyTest(TestCase):
        def test_something_that_creates_jobs(self):
            ...                      # Stuff that init jobs.
            get_worker().work(burst=True)  # Processes all jobs then stop.
            ...                      # Asserts that the job stuff is done.

Synchronous Mode
----------------

You can set the option ``ASYNC`` to ``False`` to make synchronous operation the
default for a given queue. This will cause jobs to execute immediately and on
the same thread as they are dispatched, which is useful for testing and
debugging. For example, you might add the following after you queue
configuration in your settings file:

.. code-block:: python

    # ... Logic to set DEBUG and TESTING settings to True or False ...

    # ... Regular RQ_QUEUES setup code ...

    if DEBUG or TESTING:
        for queueConfig in RQ_QUEUES.itervalues():
            queueConfig['ASYNC'] = False

Note that setting the ``is_async`` parameter explicitly when calling ``get_queue``
will override this setting.

=============
Running Tests
=============

To run ``django_rq``'s test suite::

    `which django-admin.py` test django_rq --settings=django_rq.tests.settings --pythonpath=.

===================
Deploying on Ubuntu
===================

Create an rqworker service that runs the high, default, and low queues.

sudo vi /etc/systemd/system/rqworker.service

.. code-block:: bash

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

Enable and start the sevice

.. code-block:: bash

    sudo systemctl enable rqworker
    sudo systemctl start rqworker

===================
Deploying on Heroku
===================

Add `django-rq` to your `requirements.txt` file with:

.. code-block:: bash

    pip freeze > requirements.txt

Update your `Procfile` to:

.. code-block:: bash

    web: gunicorn --pythonpath="$PWD/your_app_name" config.wsgi:application

    worker: python your_app_name/manage.py rqworker high default low

Commit and re-deploy. Then add your new worker with:

.. code-block:: bash

    heroku scale worker=1

=======================
Django Suit Integration
=======================

You can use `django-suit-rq <https://github.com/gsmke/django-suit-rq>`__ to make your
admin fit in with the django-suit styles.

=========
Changelog
=========

See `changelog <https://github.com/rq/django-rq/blob/master/CHANGELOG.md>`.


.. |Build Status| image:: https://secure.travis-ci.org/rq/django-rq.svg?branch=master
   :target: https://travis-ci.org/rq/django-rq
