from django.urls import reverse

from .base import AppTestCase


class CatalogTests(AppTestCase):
    def test_multiple_filters_apply_together(self):
        wanted = self.make_track(
            title='Wanted song',
            genre='indie',
            mood='relax',
            tempo='slow',
            release_year=2020,
            duration_seconds=200,
            lyrics='Lyrics',
            is_explicit=True
        )
        response = self.client.get(
            reverse('home'),
            {
                'genre': 'indie',
                'mood': 'relax',
                'tempo': 'slow',
                'release_year_from': 2019,
                'release_year_to': 2021,
                'duration': 'standard',
                'has_lyrics': 'on',
                'explicit': 'on'
            }
        )
        self.assertEqual(list(response.context['tracks']), [wanted])

    def test_invalid_year_range_is_reported(self):
        response = self.client.get(reverse('home'), {'release_year_from': 2025, 'release_year_to': 2020})
        self.assertContains(response, 'Начальный год не может')
        self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_duration_boundaries_are_not_ambiguous(self):
        at_three = self.make_track(duration_seconds=180)
        at_five = self.make_track(duration_seconds=300)
        standard = self.client.get(reverse('home'), {'duration': 'standard'}).context['tracks']
        self.assertEqual(set(standard), {at_three, at_five})
        short = self.client.get(reverse('home'), {'duration': 'short'}).context['tracks']
        self.assertIn(self.track, short)
        self.assertNotIn(at_three, short)

    def test_popularity_and_likes_sorting(self):
        popular = self.make_track(plays_count=20)
        self.track.likes.add(self.listener)
        self.assertEqual(self.client.get(reverse('home'), {'sort': 'popular'}).context['tracks'][0], popular)
        self.assertEqual(self.client.get(reverse('home'), {'sort': 'liked'}).context['tracks'][0], self.track)

    def test_private_playlist_title_is_not_searchable(self):
        self.make_album(owner=self.listener, is_public=False, title='Private secret')
        response = self.client.get(reverse('home'), {'search': 'Private secret'})
        self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_release_duration_includes_all_tracks_after_genre_filter(self):
        long_track = self.make_track(duration_seconds=400, genre='indie')
        album = self.make_album(tracks=[self.track, long_track])
        response = self.client.get(reverse('release_list'), {'genre': 'rock', 'duration': 'long'})
        self.assertIn(album, response.context['albums'])
        result = response.context['albums'][0]
        self.assertEqual(result.total_duration, 520)
        self.assertEqual(result.track_count, 2)

    def test_artist_analytics_supports_both_periods(self):
        self.login(self.artist_user)
        for period in (7, 30):
            response = self.client.get(reverse('artist_dashboard'), {'period': period})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['chart_values']), period)
