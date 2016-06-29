# -*- coding: utf-8 -*-
from optparse import make_option

from django.core.management.base import BaseCommand

from django_rq import get_scheduler
from django_rq import settings


class Command(BaseCommand):
    help = 'Remove all cronjobs from scheduer and install new ones defined in RQ_CRONJOBS setting (by default). ' \
           'See possible options to get more...'
    option_list = BaseCommand.option_list + (
        make_option(
            '-i',
            '--install',
            action='store_true',
            dest='install',
            default=False,
            help='Limit only to installing cronjobs defined in RQ_CRONJOBS setting.'
        ),
        make_option(
            '-r',
            '--remove',
            action='store_true',
            dest='remove',
            default=False,
            help='Limit only to removing all cronjobs from scheduler.'
        ),
        make_option(
            '-l',
            '--list',
            action='store_true',
            dest='list',
            default=False,
            help='List cronjobs defined in RQ_CRONJOBS setting and defined in scheduler.'
        ),
    )

    def handle(self, *args, **options):
        scheduler = get_scheduler()

        if options.get('list'):
            print('Cronjobs from scheduler:')
            for cronjob in scheduler.get_jobs():
                print('* {}'.format(cronjob))
            print('')
            print('Cronjobs defined in settings.RQ_CRONJOBS:')
            for cronjob_entry in settings.CRONJOBS:
                print('* {}'.format(cronjob_entry))
            print('')
        else:
            reinstall = not (options.get('install') or options.get('remove'))

            if reinstall or options.get('remove'):
                print('Removed cronjobs from scheduler:')
                for cronjob in scheduler.get_jobs():
                    print('* {}'.format(cronjob))
                    cronjob.delete()
                print('')

            if reinstall or options.get('install'):
                print('Cronjobs installed from settings.RQ_CRONJOBS:')
                for cronjob_entry in settings.CRONJOBS:
                    if type(cronjob_entry) is dict:
                        args = []
                        kwargs = cronjob_entry
                    else:
                        args = cronjob_entry
                        kwargs = {}
                    cronjob = scheduler.cron(
                        *args, **kwargs
                    )
                    print('* {}'.format(cronjob))
                print('')
