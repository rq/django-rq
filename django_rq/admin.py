from django.contrib import admin

from . import settings


if settings.SHOW_ADMIN_LINK:
    admin.site.index_template = 'django_rq/index.html'