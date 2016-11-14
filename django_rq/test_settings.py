# -*- coding: utf-8 -*-
import os

REDIS_HOST = os.environ.get("REDIS_HOST", 'localhost')

SECRET_KEY = 'a'

# Detect whether either django-redis or django-redis-cache is installed. This
# is only really used to conditionally configure options for the unit tests.
# In actually usage, no such check is necessary.
try:
    import redis_cache
    if hasattr(redis_cache, 'get_redis_connection'):
        REDIS_CACHE_TYPE = 'django-redis'
    else:
        REDIS_CACHE_TYPE = 'django-redis-cache'
except ImportError:
    REDIS_CACHE_TYPE = 'none'
try:
    from django.utils.log import NullHandler
    nullhandler = 'django.utils.log.NullHandler'
except:
    nullhandler = 'logging.NullHandler'

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

if REDIS_CACHE_TYPE == 'django-redis':
    CACHES = {
        'django-redis': {
            'BACKEND': 'redis_cache.cache.RedisCache',
            'LOCATION': '%s:6379:2' % REDIS_HOST,
            'KEY_PREFIX': 'django-rq-tests',
            'OPTIONS': {
                'CLIENT_CLASS': 'redis_cache.client.DefaultClient',
                'MAX_ENTRIES': 5000,
            },
        },
    }
elif REDIS_CACHE_TYPE == 'django-redis-cache':
    CACHES = {
        'django-redis-cache': {
            'BACKEND': 'redis_cache.cache.RedisCache',
            'LOCATION': '%s:6379' % REDIS_HOST,
            'KEY_PREFIX': 'django-rq-tests',
            'OPTIONS': {
                'DB': 2,
                'MAX_ENTRIES': 5000,
            },
        },
    }

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
            'class': nullhandler,
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
        'HOST': REDIS_HOST,
        'PORT': 6379,
        'DB': 0,
        'DEFAULT_TIMEOUT': 500
    },
    'test': {
        'HOST': REDIS_HOST,
        'PORT': 1,
        'DB': 1,
    },
    'test1': {
        'HOST': REDIS_HOST,
        'PORT': 1,
        'DB': 1,
        'DEFAULT_TIMEOUT': 400,
        'QUEUE_CLASS': 'django_rq.tests.DummyQueue'
    },
    'test2': {
        'HOST': REDIS_HOST,
        'PORT': 1,
        'DB': 1,
    },
    'test3': {
        'HOST': REDIS_HOST,
        'PORT': 6379,
        'DB': 1,
    },
    'async': {
        'HOST': REDIS_HOST,
        'PORT': 6379,
        'DB': 1,
        'ASYNC': False,
    },
    'url': {
        'URL': 'redis://username:password@host:1234/',
        'DB': 4,
    },
    'url_with_db': {
        'URL': 'redis://username:password@host:1234/5',
    },
    'url_default_db': {
        'URL': 'redis://username:password@host:1234',
    },
    'django_rq_test': {
        'HOST': REDIS_HOST,
        'PORT': 6379,
        'DB': 0,
    },
    'django_rq_test2': {
        'HOST': REDIS_HOST,
        'PORT': 6379,
        'DB': 0,
    },
}
RQ = {
    'AUTOCOMMIT': False,
}

if REDIS_CACHE_TYPE == 'django-redis':
    RQ_QUEUES['django-redis'] = {'USE_REDIS_CACHE': 'django-redis'}
elif REDIS_CACHE_TYPE == 'django-redis-cache':
    RQ_QUEUES['django-redis-cache'] = {'USE_REDIS_CACHE': 'django-redis-cache'}

ROOT_URLCONF = 'django_rq.tests.urls'

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, "templates")],
        'APP_DIRS': False,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
        },
    },
]


MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)
