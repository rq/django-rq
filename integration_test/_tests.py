# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import logging
import os
import signal
import subprocess
import sys
import time
import unittest
from urllib.parse import urlunsplit import urlunsplit

import psycopg2
import requests
from django.conf import settings

DJANGO_SETTINGS_MODULE = "integration_test.settings"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS_MODULE)

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


class Process(object):
    @staticmethod
    def _command(args):
        return list(args)

    @classmethod
    def run(cls, *args):
        subprocess.check_call(cls._command(args))

    def __init__(self, *args):
        self.args = list(args)

    def start(self):
        self.process = subprocess.Popen(self._command(self.args), preexec_fn=os.setsid)
        logger.info("START PROCESS args:{} pid:{}".format(self.args, self.process.pid))
        time.sleep(1)

    def stop(self):
        # to be sure we kill all the children:
        os.killpg(self.process.pid, signal.SIGTERM)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class DjangoCommand(Process):
    @staticmethod
    def _command(args):
        return ["./manage.py"] + list(args) + ["--settings", DJANGO_SETTINGS_MODULE]


def terminate_all_postgres_connections(profile="default"):
    db_settings = settings.DATABASES[profile]
    conn_params = {
        'database': 'template1',
        'user': db_settings["USER"],
        'password': db_settings["PASSWORD"],
        'host': db_settings["HOST"],
        'port': db_settings["PORT"],
    }
    with psycopg2.connect(**conn_params) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = %s
        """, (db_settings["NAME"], ))


class IntegrationTest(unittest.TestCase):
    ADDRPORT = "127.0.0.1:8000"
    HOME_URL = urlunsplit(("http", ADDRPORT, "/", "", ""))

    def setUp(self):
        DjangoCommand.run("flush", "--noinput")
        # self.site = DjangoCommand("runserver", self.ADDRPORT)
        self.site = Process(
            "gunicorn", "-b", self.ADDRPORT,
            "--timeout", "600",  # useful for worker debugging
            "integration_test.wsgi:application")
        self.site.start()

    def tearDown(self):
        self.site.stop()

    def assertFailure(self):
        r = requests.get(self.HOME_URL)
        self.assertEqual(r.status_code, 500)

    def assertEntries(self, expected):
        r = requests.get(self.HOME_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, "Entries: {}".format(",".join(expected)))

    def enqueue(self, name):
        r = requests.post(self.HOME_URL, {"name": name})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, "Enqueued")

    def test_db_is_empty(self):
        self.assertEntries([])

    def test_burst(self):
        self.enqueue("first")
        DjangoCommand.run("rqworker", "--burst")
        self.assertEntries(["first"])

    def test_site_fails_and_the_reconnects(self):
        self.enqueue("first")
        DjangoCommand.run("rqworker", "--burst")

        terminate_all_postgres_connections()

        # the DB connection is gone, so the worker must first detect the problem:
        self.assertFailure()
        # now the gunicorn worker is ok again:
        self.assertEntries(["first"])

    def test_worker_lost_connection(self):
        with DjangoCommand("rqworker") as worker:
            self.enqueue("first")
            time.sleep(2) # wait for the worker to do the job
            self.assertEntries(["first"]) # job is done

            terminate_all_postgres_connections()

            self.enqueue("second")
            time.sleep(2) # wait for the worker to do the job

            self.assertFailure() # let the gunicorn worker reconnect
            self.assertEntries(["first", "second"]) # work is done


if __name__ == '__main__':
    unittest.main()
