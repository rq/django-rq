from typing import Any, Dict, Optional

from django.contrib import admin
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.urls import reverse

from . import views, settings, models


class QueueAdmin(admin.ModelAdmin):
    """Admin View for Django-RQ Queue"""

    def has_add_permission(self, request):
        return False  # Hide the admin "+ Add" link for Queues

    def has_change_permission(self, request: HttpRequest, obj: Optional[Any] = None) -> bool:
        return True

    def has_module_permission(self, request: HttpRequest):
        """
        return True if the given request has any permission in the given
        app label.

        Can be overridden by the user in subclasses. In such case it should
        return True if the given request has permission to view the module on
        the admin index page and access the module's index page. Overriding it
        does not restrict access to the add, change or delete views. Use
        `ModelAdmin.has_(add|change|delete)_permission` for that.
        """
        return request.user.has_module_perms('django_rq')  # type: ignore[union-attr]

    def changelist_view(self, request: HttpRequest, extra_context: Optional[Dict[str, Any]] = None) -> HttpResponse:
        """The 'change list' admin view for this model."""
        # proxy request to stats view
        return views.stats(request)


class RQDashboardApp:
    name = 'rq_dashboard'

    def get_app_list(self, request, app_list):
        """
        Return a custom app list by adding RQ Dashboard link to the admin index.
        """
        rq_app = {
            'name': 'Django RQ',
            'app_label': 'django_rq',
            'app_url': reverse('rq_home'),
            'has_module_perms': True,
            'models': [{
                'name': 'Queues',
                'object_name': 'Queue',
                'admin_url': reverse('rq_home'),
                'view_only': False,
                'perms': {'add': False, 'change': False, 'delete': False}
            }],
        }

        return app_list + [rq_app]

def setup_admin_integration():
    """
    Add RQ Dashboard to admin site without template override.
    Call this function in your AppConfig.ready()
    """
    # Get admin site instance
    admin_site = admin.site

    # Store original get_app_list method
    if not hasattr(admin_site, '_original_get_app_list'):
        admin_site._original_get_app_list = admin_site.get_app_list

    # Define the wrapper function
    def get_app_list(request, app_list=None):
        if app_list is None:
            app_list = admin_site._original_get_app_list(request)
        return RQDashboardApp().get_app_list(request, app_list)

    # Replace the get_app_list method
    admin_site.get_app_list = get_app_list
