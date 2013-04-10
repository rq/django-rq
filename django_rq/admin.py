from django.contrib import admin
from django_rq import settings


if settings.SHOW_ADMIN_LINK:
    admin.site.index_template = 'django_rq/index.html'