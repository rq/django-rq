=========
Django-RQ
=========

.. image:: https://secure.travis-ci.org/ui/django-rq.png

Django integration with `RQ <https://github.com/nvie/rq>`_, a `Redis <http://redis.io/>`_
based Python queuing library. `Django-RQ <https://github.com/ui/django-rq>`_ is a
simple app that allows you to configure your queues in django's ``settings.py``
and easily use them in your project.

============
Requirements
============

* `Django <https://www.djangoproject.com/>`_
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
        },
        'high': {
            'URL': os.getenv('REDISTOGO_URL', 'redis://localhost:6379'), # If you're on Heroku
            'DB': 0,
        },
        'low': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
    }

* Include ``django_rq.urls`` in your ``urls.py``:

.. code-block:: python

    urlpatterns += patterns('',
        url(r'^admin/django_rq/', include('django_rq.urls')),
        # the core django admin URL declaration must appear *after* the
        # django_rq URL declaration otherwise you will receive a 404
        url(r'^admin/', include(admin.site.urls)),
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
    worker.run()
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


Support for RQ Scheduler
------------------------

If you have `RQ Scheduler <https://github.com/ui/rq-scheduler>`_ installed,
you can also use the ``get_scheduler`` function to return a ``Scheduler``
instance for queues defined in settings.py's ``RQ_QUEUES``. For example:

.. code-block:: python

    import django_rq
    scheduler = django_rq.get_scheduler('default')
    job = scheduler.enqueue_at(datetime(2020, 10, 10), func)


Queue statistics
----------------

``django_rq`` also provides a very simple dashboard to monitor the status of
your queues at ``/admin/django_rq/``.

If you need a more sophisticated monitoring tool for RQ, you could also try
`rq-dashboard <https://github.com/nvie/rq-dashboard>`_.


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
        },
        'loggers': {
            "rq.worker": {
                "handlers": ["rq_console"],
                "level": "DEBUG" 
            },
        }
    }


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


=============
Running Tests
=============

To run ``django_rq``'s test suite::

    django-admin.py test django_rq --settings=django_rq.tests.settings --pythonpath=.

=========
Changelog
=========

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
