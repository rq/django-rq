import os
from distutils.version import LooseVersion

from django.core.management.base import BaseCommand
from django.utils.version import get_version
from django_rq import get_scheduler


class Command(BaseCommand):
    """
    Runs RQ scheduler
    """
    help = __doc__
    args = '<queue>'

    def add_arguments(self, parser):
        parser.add_argument('--pid', action='store', dest='pid',
                            default=None, help='PID file to write the scheduler`s pid into')
        parser.add_argument('--interval', '-i', type=int, dest='interval',
                            default=60, help="""How often the scheduler checks for new jobs to add to the
                            queue (in seconds).""")
        parser.add_argument('--queue', dest='queue', default='default',
                            help="Name of the queue used for scheduling.",)

        if LooseVersion(get_version()) >= LooseVersion('1.9'):
            parser.add_argument('args', nargs='*')

    def handle(self, *args, **options):
        pid = options.get('pid')
        if pid:
            with open(os.path.expanduser(pid), "w") as fp:
                fp.write(str(os.getpid()))

        scheduler = get_scheduler(
            name=options.get('queue'), interval=options.get('interval'))
        scheduler.run()
