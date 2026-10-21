import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ImportedTrack:
    external_id: str
    title: str
    artist_name: str
    genre: str
    release_year: int | None
    duration_seconds: int | None
    source_url: str
    audio_url: str
    cover_url: str
    license_name: str
    attribution: str


class JamendoAdapter:
    endpoint = 'https://api.jamendo.com/v3.0/tracks/'

    def __init__(self, client_id, timeout=15):
        self.client_id = client_id
        self.timeout = timeout

    def fetch_tracks(self, query='', limit=20):
        params = {
            'client_id': self.client_id,
            'format': 'json',
            'limit': min(max(limit, 1), 200),
            'include': 'musicinfo',
            'audioformat': 'mp32',
        }
        if query:
            params['search'] = query
        request = Request(f'{self.endpoint}?{urlencode(params)}', headers={'User-Agent': 'SoundMess/1.0'})
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        return [self._map_track(item) for item in payload.get('results', [])]

    @staticmethod
    def _map_track(item):
        release_year = None
        release_date = item.get('releasedate', '')
        if release_date[:4].isdigit():
            release_year = int(release_date[:4])
        duration = item.get('duration')
        return ImportedTrack(
            external_id=str(item['id']),
            title=item.get('name', '').strip(),
            artist_name=item.get('artist_name', '').strip(),
            genre=(item.get('musicinfo') or {}).get('tags', {}).get('genres', ['Imported'])[0],
            release_year=release_year,
            duration_seconds=int(duration) if duration else None,
            source_url=item.get('shareurl') or item.get('shorturl') or '',
            audio_url=item.get('audio') or item.get('audiodownload') or '',
            cover_url=item.get('image') or '',
            license_name=item.get('license_ccurl', ''),
            attribution=f"{item.get('artist_name', '').strip()} via Jamendo",
        )
