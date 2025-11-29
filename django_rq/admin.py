from functools import wraps
from typing import Any, Optional

from django.contrib import admin
from django.http.request import HttpRequest
from django.http.response import HttpResponse

from . import models, settings, stats_views


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

    def changelist_view(self, request: HttpRequest, extra_context: Optional[dict[str, Any]] = None) -> HttpResponse:
        """The 'change list' admin view for this model."""
        # proxy request to stats view
        return stats_views.stats(request)

    def get_urls(self):
        """
        Register Django-RQ views within Django admin.

        URLs will be available at /admin/django_rq/queue/<pattern>/
        This provides automatic integration without requiring users to edit urls.py.

        Uses two sets of URL patterns:
        - API patterns (stats_json, prometheus_metrics): NOT wrapped, support API token auth
        - Admin patterns (all other views): Wrapped with admin_view for session auth
        """
        # Import inside method to avoid circular imports
        from .urls import get_admin_urlpatterns, get_api_urlpatterns

        def wrap(view):
            """Wrap view with admin_site.admin_view for permission checking"""

            @wraps(view)
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            return wrapper

        # Get both sets of URL patterns
        api_urls = get_api_urlpatterns()  # Not wrapped - have their own auth
        admin_urls = get_admin_urlpatterns(view_wrapper=wrap)  # Wrapped with admin auth

        # Combine and add to standard ModelAdmin URLs
        return api_urls + admin_urls + super().get_urls()


# Register the Queue model with admin if enabled.
if settings.SHOW_ADMIN_LINK:
    admin.site.register(models.Queue, QueueAdmin)
