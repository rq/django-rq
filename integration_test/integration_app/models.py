from django.db import models


class MyModel(models.Model):
    name = models.TextField(unique=True)


def add_mymodel(name):
    m = MyModel(name=name)
    m.save()


# causes a DB connection at import-time
# see TestIntegration.test_worker_lost_connection
list(MyModel.objects.all())
