0.9.5
-----
* Fixed view paging for registry-based job lists. Thanks @smaccona!
* Fixed an issue where multiple failed queues may appear for the same connection. Thanks @depaolim!
* ``rqworker`` management command now closes all DB connections before executing jobs. Thanks @depaolim!
* Fixed an argument parsing bug ``rqworker`` management command. Thanks @hendi!

0.9.3
-----
* Added a ``--pid`` option to ``rqscheduler`` management command. Thanks @vindemasi!
* Added ``--queues`` option to ``rqworker`` management command. Thanks @gasket!
* Job results are now shown on admin page. Thanks @mojeto!
* Fixed a bug in interpreting ``--burst`` argument in ``rqworker`` management command. Thanks @claudep!
* Added Requeue All feature in Failed Queue's admin page. Thanks @lucashowell!
* Admin interface now shows time in local timezone. Thanks @randomguy91!
* Other minor fixes by @jeromer and @sbussetti.

0.9.2
-----
* Support for Django 1.10. Thanks @jtburchfield!
* Added ``--queue-class`` option to ``rqworker`` management command. Thanks @Krukov!

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
