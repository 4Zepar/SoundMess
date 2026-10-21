from django.apps import AppConfig


class PcStoreConfig(AppConfig):
    name = 'pc_store'

    def ready(self):
        from . import signals  # noqa: F401
