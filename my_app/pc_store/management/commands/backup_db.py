import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Создаёт согласованную резервную копию SQLite без остановки приложения.'

    def add_arguments(self, parser):
        parser.add_argument('destination', type=Path, help='Папка для резервной копии.')

    def handle(self, *args, **options):
        database = settings.DATABASES['default']
        if database['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('Эта команда поддерживает только SQLite.')
        source = Path(database['NAME']).resolve()
        if not source.is_file():
            raise CommandError('Исходная база данных не найдена.')
        destination = options['destination'].resolve()
        destination.mkdir(parents=True, exist_ok=True)
        filename = destination / f'soundmess-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3'
        with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as original:
            with sqlite3.connect(filename) as backup:
                original.backup(backup)
                result = backup.execute('PRAGMA integrity_check').fetchone()[0]
        if result != 'ok':
            raise CommandError(f'Проверка копии завершилась ошибкой: {result}')
        self.stdout.write(self.style.SUCCESS(str(filename)))
