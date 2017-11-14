import click
import time

from django.core.management.base import BaseCommand
from django_rq.utils import get_statistics


class Command(BaseCommand):
    """
    Print RQ statistics
    """
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            '-j', '--json',
            action='store_true',
            dest='json',
            help='Output statistics as JSON',
        )

        parser.add_argument(
            '-y', '--yaml',
            action='store_true',
            dest='yaml',
            help='Output statistics as YAML',
        )

        parser.add_argument(
            '-l', '--live',
            action='store_true',
            dest='live',
            help='Show live CLI dashboard',
        )

    def _print_separator(self):
        try:
            click.echo(self._separator)
        except AttributeError:
            self._separator = "-" * self.table_width
            click.echo(self._separator)

    def _print_stats_dashboard(self, statistics):
        if self.live:
            click.clear()

        click.echo()
        click.echo("Django RQ%s CLI Dashboard" % " Live" if self.live else "")
        click.echo()
        self._print_separator()

        # Header
        click.echo(
            """| %-15s|%10s |%10s |%10s |%10s |%10s |""" %
            ("Name", "Queued", "Active", "Deferred", "Finished", "Workers")
        )

        self._print_separator()

        # Print every queues in a row
        for queue in statistics["queues"]:
            click.echo(
                """| %-15s|%10s |%10s |%10s |%10s |%10s |""" %
                (queue["name"], queue["jobs"],
                 queue["started_jobs"], queue["deferred_jobs"],
                 queue["finished_jobs"], queue["workers"])
            )

        self._print_separator()

        if self.live:
            click.echo()
            click.echo("Press 'Ctrl+c' to quit")

    def handle(self, *args, **options):

        if options.get("json"):
            import json
            click.echo(json.dumps(get_statistics()))
            return

        if options.get("yaml"):
            try:
                import yaml
            except ImportError:
                click.echo("Aborting. LibYAML is not installed.")
                return
            # Disable YAML alias
            yaml.Dumper.ignore_aliases = lambda *args: True
            click.echo(yaml.dump(get_statistics(), default_flow_style=False))
            return

        if options.get("live"):
            self.live = True
        else:
            self.live = False

        # Arbitrary
        self.table_width = 78

        # Not live, just print and exit
        if not self.live:
            self._print_stats_dashboard(get_statistics())
            return

        # Abuse clicks to 'live' render CLI dashboard TODO: Use curses instead
        try:
            while True:
                self._print_stats_dashboard(get_statistics())
                time.sleep(1)
        except KeyboardInterrupt:
            pass
