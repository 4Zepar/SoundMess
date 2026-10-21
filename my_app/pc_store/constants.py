from django.db import models


class PublicationStatus(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    PENDING = 'pending', 'На проверке'
    APPROVED = 'approved', 'Опубликован'
    REJECTED = 'rejected', 'Отклонён'
    HIDDEN = 'hidden', 'Скрыт'


class ReleaseType(models.TextChoices):
    SINGLE = 'single', 'Сингл'
    ALBUM = 'album', 'Альбом'
    EP = 'ep', 'EP'
    MIXTAPE = 'mixtape', 'Микстейп'


GENRES = (
    ('rock', 'Рок'), ('hiphop', 'Хип-хоп'), ('phonk', 'Фонк'),
    ('indie', 'Инди'), ('electronic', 'Электроника'), ('pop', 'Поп'),
    ('jazz', 'Джаз'), ('classical', 'Классика'), ('other', 'Другое'),
)
MOODS = (
    ('energetic', 'Энергичный'), ('relax', 'Релакс'), ('sad', 'Грустный'),
    ('melancholic', 'Меланхоличный'), ('happy', 'Радостный'), ('neutral', 'Нейтральный'),
)
TEMPOS = (('slow', 'Медленный'), ('medium', 'Умеренный'), ('fast', 'Быстрый'))
