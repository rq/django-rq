from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .models import *

import django_rq


@csrf_exempt
def home(request):
    if request.method == 'POST':
        django_rq.enqueue(add_mymodel, request.POST["name"])
        return HttpResponse("Enqueued")
    names = [m.name for m in MyModel.objects.order_by("name")]
    return HttpResponse("Entries: {}".format(",".join(names)))
        
