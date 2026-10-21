from math import isfinite

from django.core.management.base import BaseCommand
from mutagen import File as AudioFile, MutagenError

from pc_store.models import Album, Profile, Track


class Command(BaseCommand):
    help = 'Проверяет наличие загруженных файлов. Не удаляет и не переименовывает данные.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-duration', action='store_true',
            help='Определить длительность существующих аудиофайлов и сохранить её в базе.',
        )

    def handle(self, *args, **options):
        missing = updated = 0
        for model, fields in ((Track, ('audio_file', 'cover')), (Album, ('cover',)), (Profile, ('avatar',))):
            for item in model.objects.iterator():
                for name in fields:
                    field = getattr(item, name)
                    if not field:
                        continue
                    if not field.storage.exists(field.name):
                        missing += 1
                        self.stdout.write(f'MISSING {model.__name__}#{item.pk} {name}: {field.name}')
                    elif name == 'audio_file' and options['update_duration']:
                        try:
                            with field.open('rb') as stream:
                                audio = AudioFile(stream)
                                length = audio.info.length if audio else 0
                            if not isfinite(length) or not 0 < length <= 86400:
                                raise ValueError('Некорректная длительность')
                            duration = max(1, round(length))
                            if item.duration_seconds != duration:
                                Track.objects.filter(pk=item.pk).update(duration_seconds=duration)
                                updated += 1
                        except (MutagenError, OSError, ValueError, EOFError) as error:
                            self.stderr.write(f'INVALID Track#{item.pk}: {error}')
        self.stdout.write(f'Отсутствующих файлов: {missing}. Обновлено длительностей: {updated}.')
