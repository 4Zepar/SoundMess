import mimetypes
import runpy
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.test import RequestFactory, SimpleTestCase


class JavaScriptServingTests(SimpleTestCase):
    def test_modules_are_served_as_javascript_despite_system_mime_mapping(self):
        # Reproduce Windows installations that associate .js with plain text.
        with patch.dict(mimetypes.types_map, {'.js': 'text/plain'}):
            self.assertEqual(mimetypes.guess_type('app.js')[0], 'text/plain')
            runpy.run_path(str(settings.BASE_DIR / 'my_app' / 'settings.py'))
            handler = StaticFilesHandler(None)
            for module in ('app', 'actions', 'navigation', 'player', 'http', 'session'):
                with self.subTest(module=module):
                    request = RequestFactory().get(f'/static/pc_store/js/{module}.js')
                    response = handler.serve(request)
                    try:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response['Content-Type'], 'text/javascript')
                    finally:
                        response.close()
