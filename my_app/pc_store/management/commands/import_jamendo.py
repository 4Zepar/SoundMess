import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from pc_store.importers import JamendoAdapter
from pc_store.models import Artist, Track


class Command(BaseCommand):
    help = 'Import Jamendo metadata with an optional dry-run preview.'

    def add_arguments(self, parser):
        parser.add_argument('--query', default='', help='Jamendo search query')
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--artist-username', help='Approved artist who owns imported tracks')
        parser.add_argument('--client-id', default=os.getenv('JAMENDO_CLIENT_ID'))
        parser.add_argument('--dry-run', action='store_true', help='Fetch and print metadata without database writes')

    def handle(self, *args, **options):
        if not options['client_id']:
            raise CommandError('JAMENDO_CLIENT_ID or --client-id is required')
        if not options['dry_run'] and not options['artist_username']:
            raise CommandError('--artist-username is required unless --dry-run is used')

        adapter = JamendoAdapter(options['client_id'])
        try:
            imported_tracks = adapter.fetch_tracks(options['query'], options['limit'])
        except Exception as error:
            raise CommandError(f'Jamendo request failed: {error}') from error

        if options['dry_run']:
            for track in imported_tracks:
                self.stdout.write(f'{track.external_id}: {track.title} — {track.artist_name} [{track.license_name}]')
            self.stdout.write(self.style.SUCCESS(f'Dry-run complete: {len(imported_tracks)} tracks'))
            return

        artist = Artist.objects.filter(
            user__username=options['artist_username'],
            moderation_status='approved',
        ).first()
        if not artist:
            raise CommandError('The target artist does not exist or is not approved')

        created_count = 0
        skipped_count = 0
        for imported in imported_tracks:
            if Track.objects.filter(source_provider='jamendo', source_id=imported.external_id).exists():
                skipped_count += 1
                continue
            Track.objects.create(
                artist=artist,
                title=imported.title,
                audio_file='',
                genre=imported.genre[:50],
                release_year=imported.release_year,
                duration_seconds=imported.duration_seconds,
                release_type='single',
                source_provider='jamendo',
                source_id=imported.external_id,
                license_name=imported.license_name[:200],
                attribution=imported.attribution,
                source_url=imported.source_url,
            )
            created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Import complete: created={created_count}, skipped={skipped_count}. '
            'Audio and covers were not downloaded.'
        ))
