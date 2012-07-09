=========
Django-RQ
=========

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

* Install ``django-rq``::

    pip install django-rq

* Add ``django_rq`` to ``INSTALLED_APPS`` in ``settings.py``::

    INSTALLED_APPS = (
        # other apps
        "django_rq",
    )

* Configure your queues in django's ``settings.py`` (syntax based on Django's database config) ::

    RQ_QUEUES = {
        'default': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
            'PASSWORD': 'some-password',
        },
        'high': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        },
        'low': {
            'HOST': 'localhost',
            'PORT': 6379,
            'DB': 0,
        }
    }
* Include ``django_rq.urls`` in your ``urls.py``::

    urlpatterns += patterns('',
        (r'^django_rq/', include('django_rq.urls')),
    )


=====
Usage
=====

Putting jobs in the queue
-------------------------

`Django-RQ` allows you to easily put jobs into any of the queues defined in
``settings.py``. It comes with a few utility functions:

* ``enqueue`` - push a job to the ``default`` queue::

    import django_rq
    django_rq.enqueue(func, foo, bar=baz)

* ``get_queue`` - accepts a single queue name argument (defaults to "default")
  and returns an `RQ` ``Queue`` instance for you to queue jobs into::

    import django_rq
    queue = django_rq.get_queue('high')
    queue.enqueue(func, foo, bar=baz)

* ``get_connection`` - accepts a single queue name argument (defaults to "default")
  and returns a connection to the queue's `Redis`_ server::

    import django_rq
    redis_conn = django_rq.get_connection('high')


Running workers
---------------
django_rq provides a management command that starts a worker for every queue
specified as arguments::

    python manage.py rqworker high default low


Support for RQ Scheduler
------------------------

If you have `RQ Scheduler <https://github.com/ui/rq-scheduler>`_ installed,
you can also use the ``get_scheduler`` function to return a ``Scheduler``
instance for queues defined in settings.py's ``RQ_QUEUES``. For example::

    import django_rq
    scheduler = django_rq.get_scheduler('default')
    job = scheduler.enqueue_at(datetime(2020, 10, 10), func)

Queue statistics
----------------

You can also monitor the status of your queues from ``/django_rq/``. This uses some
features that's not yet available in RQ's current stable release (0.1.3) so you'll need
to install RQ's development version from https://github.com/nvie/rq to use this feature.

If you need a more sophisticated monitoring tools for RQ, you could also try
`rq-dashboard <https://github.com/nvie/rq-dashboard>`_.
provides a more comprehensive of monitoring tools.

=========
Changelog
=========

* Version 0.2.2: "PASSWORD" key in RQ_QUEUES will now be used when connecting to Redis.
