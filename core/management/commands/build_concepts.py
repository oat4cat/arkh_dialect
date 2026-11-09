from django.core.management.base import BaseCommand

from core.concepts_pipeline import build_concepts


class Command(BaseCommand):
    help = "Полный пересчёт концептов и связей «толкование—концепт»"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Обсчитать только первые N толкований (пробный прогон)",
        )

    def handle(self, *args, **options):
        build_concepts(limit=options["limit"], stdout=self.stdout)
