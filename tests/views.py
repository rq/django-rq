from datetime import timedelta

from django.shortcuts import render

from django_rq import get_queue


def say_hello():
    return 'Hello'


def success(request):
    queue = get_queue()
    queue.enqueue(say_hello)
    queue.enqueue_in(timedelta(minutes=1), say_hello)
    return render(request, 'django_rq/test.html', {})


def error(request):
    queue = get_queue()
    queue.enqueue(say_hello)
    queue.enqueue_in(timedelta(minutes=1), say_hello)
    raise ValueError
