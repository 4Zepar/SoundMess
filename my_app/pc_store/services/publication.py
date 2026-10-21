from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from pc_store.constants import PublicationStatus
from pc_store.models import Album, Artist, ModerationAction


def require_approved_artist(user):
    try:
        artist = user.artist
    except Artist.DoesNotExist as error:
        raise ValidationError('Сначала подайте заявку артиста.') from error
    if artist.moderation_status != 'approved' or not user.is_active:
        raise ValidationError('Публикация доступна после одобрения заявки артиста.')
    return artist


def validate_release(album, tracks):
    if not album.is_public:
        return
    require_approved_artist(album.owner)
    if not tracks.exists():
        raise ValidationError('Добавьте хотя бы один трек.')
    if tracks.exclude(artist__user=album.owner).exists():
        raise ValidationError('В авторский релиз можно добавлять только свои треки.')
    if tracks.exclude(moderation_status=PublicationStatus.APPROVED).exists():
        raise ValidationError('Сначала дождитесь одобрения всех треков релиза.')
    if album.release_type == 'single' and tracks.count() != 1:
        raise ValidationError('Сингл должен содержать один трек.')


def prepare_submission(instance, *, submit):
    instance.moderation_status = PublicationStatus.PENDING if submit else PublicationStatus.DRAFT
    instance.moderation_note = ''
    instance.reviewed_at = None
    instance.reviewed_by = None
    instance.published_at = None


@transaction.atomic
def review_content(instance, *, actor, decision, note=''):
    instance = type(instance).objects.select_for_update().get(pk=instance.pk)
    owner_id = instance.owner_id if isinstance(instance, Album) else instance.artist.user_id
    if owner_id == actor.pk:
        raise ValidationError('Свой материал должен проверить другой модератор.')
    if decision not in {'approved', 'rejected', 'hidden'}:
        raise ValidationError('Неизвестное решение.')
    if decision in {'rejected', 'hidden'} and not note.strip():
        raise ValidationError('Укажите причину решения.')
    if decision == 'hidden' and instance.moderation_status != 'approved':
        raise ValidationError('Скрыть можно только опубликованный материал.')
    if decision in {'approved', 'rejected'} and instance.moderation_status not in {'pending', 'hidden'}:
        raise ValidationError('Материал должен быть отправлен на проверку.')
    if decision == 'approved':
        if isinstance(instance, Album):
            validate_release(instance, instance.tracks.all())
        else:
            require_approved_artist(instance.artist.user)
            if not instance.audio_file or not instance.audio_file.storage.exists(instance.audio_file.name):
                raise ValidationError('Аудиофайл отсутствует. Попросите артиста загрузить его заново.')
    instance.moderation_status = decision
    instance.moderation_note = note.strip()
    instance.reviewed_by = actor
    instance.reviewed_at = timezone.now()
    if decision == 'approved':
        instance.published_at = timezone.now()
    instance.save(
        update_fields=[
            'moderation_status',
            'moderation_note',
            'reviewed_by',
            'reviewed_at',
            'published_at'
        ]
    )
    ModerationAction.objects.create(
        actor=actor,
        target_type=instance._meta.model_name,
        target_id=instance.pk,
        action=decision,
        note=note
    )
    return instance
