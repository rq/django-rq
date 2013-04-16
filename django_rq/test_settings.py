# -*- coding: utf-8 -*-


INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django_rq',
]


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

try:
    SECRET_KEY = '5'
    import redis_cache
    CACHES = {
        'redis-cache': {
            'BACKEND': 'redis_cache.cache.RedisCache',
            'LOCATION': 'localhost:6379:2',
            'KEY_PREFIX': 'django-rq-tests',
            'OPTIONS': {
                'CLIENT_CLASS': 'redis_cache.client.DefaultClient',
                'MAX_ENTRIES': 5000,
            },
        },
    }
except ImportError:
    redis_cache = None

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
            #"class": "logging.StreamHandler",
            "class": "rq.utils.ColorizingStreamHandler",
            "formatter": "rq_console",
            "exclude": ["%(asctime)s"],
        },
        'null': {
            'level': 'DEBUG',
            'class': 'django.utils.log.NullHandler',
        },
    },
    'loggers': {
        "rq.worker": {
            "handlers": ['null'],
            "level": "ERROR" 
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
    },
    'django_rq_test': {
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
    },
    'redis-cache': {
        'REDIS_CACHE': 'redis-cache',
    }
}

ROOT_URLCONF = 'django_rq.tests.urls'

SECRET_KEY = 'a'

TEMPLATE_LOADERS = (
    'django.template.loaders.app_directories.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.request",
)