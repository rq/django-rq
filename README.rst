=========
Django RQ
=========

Django integration with `rq <https://github.com/nvie/rq>`_, a Redis based
Python queuing library. django_rq is a simple app that allows you to configure
your queues in django's ``settings.py`` and easily use them in your project. 


============
Installation
============

* Put django_rq in your Python Path
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

django_rq allows you to easily use any of the queues defined in ``settings.py``

* enqueue - push a job to the ``default`` queue::
    
    import django_rq
    django_rq.enqueue(func, foo, bar=baz)

* get_queue - returns an rq ``Queue`` instance::
    
    import django_rq
    django_rq.get_queue('test').enqueue(func, foo, bar=baz)


Running workers
---------------
django_rq provides a management command that starts a worker for every queue
defined in ``settings.py``::
    
    python manage.py rqworkers


Queue statistics
----------------

You can also monitor the status of your queues from ``/django_rq/``.