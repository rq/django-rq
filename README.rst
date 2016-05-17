=========
Django-RQ
=========

|Build Status|

Django integration with `RQ <https://github.com/nvie/rq>`_, a `Redis <http://redis.io/>`_
based Python queuing library. `Django-RQ <https://github.com/ui/django-rq>`_ is a
simple app that allows you to configure your queues in django's ``settings.py``
and easily use them in your project.

============
Requirements
============

* `Django <https://www.djangoproject.com/>`_ (1.5+)
* `RQ`_

============
Installation
============

* Install ``django-rq`` (or `download from PyPI <http://pypi.python.org/pypi/django-rq>`_):

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

    urlpatterns += patterns('',
        url(r'^django-rq/', include('django_rq.urls')),
    )

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

* ``get_queue`` - accepts a single queue name argument (defaults to "default")
  and returns an `RQ` ``Queue`` instance for you to queue jobs into:

.. code-block:: python

    import django_rq
    queue = django_rq.get_queue('high')
    queue.enqueue(func, foo, bar=baz)

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


Running workers
---------------
django_rq provides a management command that starts a worker for every queue
specified as arguments::

    python manage.py rqworker high default low

If you want to run ``rqworker`` in burst mode, you can pass in the ``--burst`` flag::

    python manage.py rqworker high default low --burst

If you need to use a custom worker class, you can pass in the ``--worker-class`` flag
with the path to your worker::

    python manage.py rqworker high default low --worker-class 'path.to.GeventWorker'

Support for RQ Scheduler
------------------------

If you have `RQ Scheduler <https://github.com/ui/rq-scheduler>`_ installed,
you can also use the ``get_scheduler`` function to return a ``Scheduler``
instance for queues defined in settings.py's ``RQ_QUEUES``. For example:

.. code-block:: python

    import django_rq
    scheduler = django_rq.get_scheduler('default')
    job = scheduler.enqueue_at(datetime(2020, 10, 10), func)

You can use also use the management command ``rqscheduler`` to start the scheduler::

    python manage.py rqscheduler

Support for django-redis and django-redis-cache
-----------------------------------------------

If you have `django-redis <https://django-redis.readthedocs.org/>`_ or
`django-redis-cache <https://github.com/sebleier/django-redis-cache/>`_
installed, you can instruct django_rq to use the same connection information
from your Redis cache. This has two advantages: it's DRY and it takes advantage
of any optimization that may be going on in your cache setup (like using
connection pooling or `Hiredis <https://github.com/redis/hiredis>`_.)

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

Queue statistics
----------------

``django_rq`` also provides a dashboard to monitor the status of your queues at
``/django-rq/`` (or whatever URL you set in your ``urls.py`` during installation.

You can also add a link to this dashboard link in ``/admin`` by adding
``RQ_SHOW_ADMIN_LINK = True`` in ``settings.py``. Be careful though, this will
override the default admin template so it may interfere with other apps that
modifies the default admin template.


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

For more info, refer to `Raven's documentation <http://raven.readthedocs.org/>`_.

Testing tip
-----------

For an easier testing process, you can run a worker synchronously this way:

.. code-block:: python

    from django.test impor TestCase
    from django_rq import get_worker

    class MyTest(TestCase):
        def test_something_that_creates_jobs(self):
            ...                      # Stuff that init jobs.
            get_worker().work(burst=True)  # Processes all jobs then stop.
            ...                      # Asserts that the job stuff is done.

Synchronous mode
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

Note that setting the ``async`` parameter explicitly when calling ``get_queue``
will override this setting.

=============
Running Tests
=============

To run ``django_rq``'s test suite::

    `which django-admin.py` test django_rq --settings=django_rq.test_settings --pythonpath=.


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

You can use `django-suit-rq <https://github.com/gsmke/django-suit-rq>`_ to make your
admin fit in with the django-suit styles.

=========
Changelog
=========

0.9.1
-----
* Added ``-i`` and ``--queue`` options to `rqscheduler` management command. Thanks @mbodock and @sbussetti!
* Added ``--pid`` option to ``rqworker`` management command. Thanks @ydaniv!
* Admin interface fixes for Django 1.9. Thanks @philippbosch!
* Compatibility fix for ``django-redis-cache``. Thanks @scream4ik!
* **Backward incompatible**: Exception handlers are now defined via ``RQ_EXCEPTION_HANDLERS`` in ``settings.py``. Thanks @sbussetti!
* Queues in django-admin are now sorted by name. Thanks @pnuckowski! 



0.9.0
-----
* Support for Django 1.9. Thanks @aaugustin and @viaregio!
* ``rqworker`` management command now accepts ``--worker-ttl`` argument. Thanks pnuckowski!
* You can now easily specify custom ``EXCEPTION_HANDLERS`` in ``settings.py``. Thanks @xuhcc!
* ``django-rq`` now requires RQ >= 0.5.5

0.8.0
-----
* You can now view deferred, finished and currently active jobs from admin interface.
* Better support for Django 1.8. Thanks @epicserve and @seiryuz!
* Requires RQ >= 0.5.
* You can now use `StrictRedis` with Django-RQ. Thanks @wastrachan!

0.7.0
-----
* Added ``rqenqueue`` management command for easy scheduling of tasks (e.g via cron).
  Thanks @jezdez!
* You can now bulk delete/requeue jobs from the admin interface. Thanks @lechup!
* ``DEFAULT_TIMEOUT`` for each queue can now be configured via ``settings.py``.
  Thanks @lechup!

0.6.2
-----
* Compatibility with ``RQ`` >= 0.4.0
* Adds the ability to clear a queue from admin interface. Thanks @hvdklauw!
* ``rq_job_detail`` now returns a 404 instead of 500 when fetching a non existing job.
* ``rqworker`` command now supports ``-name`` and ``--worker-class`` parameters.

0.6.1
-----
* Adds compatibility with ``django-redis`` >= 3.4.0

0.6.0
-----
* Python 3 compatibility
* Added ``rqscheduler`` management command
* ``get_queue`` and ``get_queues`` now accept ``autocommit`` argument


0.5.1
-----
* Bugfix to ``DjangoRQ`` class


0.5.0
-----
* Added ``ASYNC`` option to ``RQ_QUEUES``
* Added ``get_failed_queue`` shortcut
* Django-RQ can now reuse existing ``django-redis`` cache connections
* Added an experimental (and undocumented) ``AUTOCOMMIT`` option, use at your own risk


0.4.7
-----
* Make admin template override optional.

0.4.6
-----
* ``get_queue`` now accepts ``async`` and ``default_timeout`` arguments
* Minor updates to admin interface

0.4.5
-----
* Added the ability to requeue failed jobs in the admin interface
* In addition to deleting the actual job from Redis, job id is now also
  correctly removed from the queue
* Bumped up ``RQ`` requirement to 0.3.4 as earlier versions cause logging to fail
  (thanks @hugorodgerbrown)

Version 0.4.4
-------------
* ``rqworker`` management command now uses django.utils.log.dictConfig so it's
  usable on Python 2.6

Version 0.4.3
-------------

* Added ``--burst`` option to ``rqworker`` management command
* Added support for Python's ``logging``, introduced in ``RQ`` 0.3.3
* Fixed a bug that causes jobs using RQ's new ``get_current_job`` to fail when
  executed through the ``rqworker`` management command

Version 0.4.2
-------------
Fixed a minor bug in accessing `rq_job_detail` view.

Version 0.4.1
-------------
More improvements to `/admin/django_rq/`:

* Views now require staff permission
* Now you can delete jobs from queue
* Failed jobs' tracebacks are better formatted

Version 0.4.0
-------------
Greatly improved `/admin/django_rq/`, now you can:

* See jobs in each queue, including failed queue
* See each job's detailed information

Version 0.3.2
-------------
* Simplified ``@job`` decorator syntax for enqueuing to "default" queue.

Version 0.3.1
-------------
* Queues can now be configured using the URL parameter in ``settings.py``.

Version 0.3.0
-------------
* Added support for RQ's ``@job`` decorator
* Added ``get_worker`` command

Version 0.2.2
-------------
* "PASSWORD" key in RQ_QUEUES will now be used when connecting to Redis.


.. |Build Status| image:: https://secure.travis-ci.org/ui/django-rq.png?branch=master
   :target: https://travis-ci.org/ui/django-rq
