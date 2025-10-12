from unittest import TestCase

from ..cron import DjangoCronScheduler
from ..utils import get_cron_schedulers


class UtilsTest(TestCase):
    def test_get_cron_schedulers(self):
        """Test get_cron_schedulers returns DjangoCronScheduler instances for unique connections."""
        schedulers = get_cron_schedulers()

        self.assertIsInstance(schedulers, list)
        self.assertEqual(len(schedulers), 7)

        for scheduler in schedulers:
            self.assertIsInstance(scheduler, DjangoCronScheduler)
            self.assertIsNotNone(scheduler.connection)
            self.assertTrue(hasattr(scheduler.connection, "ping"))
