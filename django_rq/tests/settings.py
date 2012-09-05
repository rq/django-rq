# -*- coding: utf-8 -*-


INSTALLED_APPS = ['django_rq']


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}


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
    },
    'test2': {
        'HOST': 'localhost',
        'PORT': 1,
        'DB': 1,
    },
    'test3': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 1,
    },
    'url': {
        'URL': 'redis://username:password@host:1234/',
        'DB': 4,
    }
}

