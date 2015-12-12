# -*- coding: utf-8 -*-

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
            'LOCATION': 'localhost:6379:2',
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
            'LOCATION': 'localhost:6379',
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
        'HOST': 'localhost',
        'PORT': 6379,
        'DB': 0,
        'DEFAULT_TIMEOUT': 500
    },
    'test': {
        'HOST': 'localhost',
        'PORT': 1,
        'DB': 1,
    },
    'test1': {
        'HOST': 'localhost',
        'PORT': 1,
        'DB': 1,
        'DEFAULT_TIMEOUT': 400
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
    'async': {
        'HOST': 'localhost',
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
        'HOST': 'localhost',
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
