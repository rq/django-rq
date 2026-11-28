from __future__ import annotations

from collections.abc import Callable

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

def permission_migration(
    *, old: str, new: str
) -> Callable[[StateApps, BaseDatabaseSchemaEditor], None]:
    def migrate(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
        try:
            ContentType = apps.get_model("contenttypes", "ContentType")
            Permission = apps.get_model("auth", "Permission")
            Dashboard = apps.get_model("django_rq", "Dashboard")
        except LookupError:
            return

        Permission._default_manager.filter(
            content_type=ContentType._default_manager.get_for_model(Dashboard),
            codename=old,
        ).update(codename=new)

    return migrate


class Migration(migrations.Migration):
    dependencies = [('django_rq', '0002_delete_queue_create_dashboard')]

    operations = [
        migrations.AlterModelOptions(
            name='dashboard',
            options={
                'default_permissions': (),
                'managed': False,
                'permissions': (('admin', 'Access admin page'),),
                'verbose_name': 'Django-RQ',
                'verbose_name_plural': 'Django-RQ',
            },
        ),
        migrations.RunPython(
            permission_migration(old="view", new="admin"),
            permission_migration(old="admin", new="view"),
        )
    ]
