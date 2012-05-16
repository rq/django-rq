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

* Put django_rq in your Python Path (installation via pip coming soon)
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
        },
        'test': {
            'HOST': 'localhost',
            'PORT': 1,
            'DB': 1,
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
    queue = django_rq.get_queue('test')
    queue.enqueue(func, foo, bar=baz)

* ``get_connection`` - accepts a single queue name argument (defaults to "default")
  and returns a connection to the queue's `Redis`_ server::

    import django_rq
    redis_conn = django_rq.get_connection('test')


Running workers
---------------
django_rq provides a management command that starts a worker for every queue
defined in ``settings.py``::
    
    python manage.py rqworkers


Queue statistics
----------------

You can also monitor the status of your queues from ``/django_rq/``.