from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('django_rq', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Queue',
            new_name='Dashboard',
        ),
        migrations.AlterModelOptions(
            name='Dashboard',
            options={
                'verbose_name': 'Django-RQ',
                'verbose_name_plural': 'Django-RQ',
                'permissions': [['view', 'Access admin page']],
                'managed': False,
                'default_permissions': (),
            },
        ),
    ]
