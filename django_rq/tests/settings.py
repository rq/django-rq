# -*- coding: utf-8 -*-


INSTALLED_APPS = ['django_rq']


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "%(asctime)s %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            #"class": "logging.StreamHandler",
            "class": "rq.utils.ColorizingStreamHandler",
            "formatter": "console",
            "exclude": ["%(asctime)s"],
        },
    },
    'loggers': {
        "rq.worker": {
            "handlers": ["console"],
            "level": "DEBUG" 
        },
    }
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

