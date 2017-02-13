from django.db import models


class MyModel(models.Model):
    name = models.TextField(unique=True)


def add_mymodel(name):
    m = MyModel(name=name)
    m.save()
