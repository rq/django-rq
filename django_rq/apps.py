from django.apps import AppConfig


class DjangoRqAdminConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "django_rq"

    def ready(self):
        from .admin import setup_admin_integration
        setup_admin_integration()
