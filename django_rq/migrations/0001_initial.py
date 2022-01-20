from django.db import migrations, models


class Migration(migrations.Migration):
    """Create Django contenttype for queue"""

    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='Queue',
            fields=[
                # Does not create any table / fields in the database
                # Registers the Queue model as migrated
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID'
                    )
                ),
            ],
            options={
                # Enables the Django contenttype framework for django_rq
                'permissions': [['view', 'Access admin page']],
                'managed': False,
                'default_permissions': (),
            },
        ),
    ]
