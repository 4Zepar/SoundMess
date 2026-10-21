from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from pc_store.models import Donation, Wallet, WalletTransaction


def _change_balance(wallet, amount_cents):
    query = Wallet.objects.filter(pk=wallet.pk)
    if amount_cents < 0:
        query = query.filter(balance_cents__gte=-amount_cents)
    if not query.update(balance_cents=F('balance_cents') + amount_cents, updated_at=timezone.now()):
        raise ValidationError('Недостаточно средств на балансе.')
    wallet.refresh_from_db()


@transaction.atomic
def adjust_balance(*, user, amount_cents, operation_key, description):
    if not amount_cents:
        raise ValidationError('Сумма должна отличаться от нуля.')
    wallet, _ = Wallet.objects.get_or_create(user=user)
    entry, created = WalletTransaction.objects.get_or_create(
        operation_key=operation_key,
        defaults={
            'wallet': wallet,
            'amount_cents': amount_cents,
            'balance_after_cents': 0,
            'description': description
        },
    )
    if not created:
        if entry.wallet_id != wallet.pk or entry.amount_cents != amount_cents:
            raise ValidationError('Параметры операции не совпадают с подтверждёнными.')
        return entry
    _change_balance(wallet, amount_cents)
    entry.balance_after_cents = wallet.balance_cents
    entry.save(update_fields=['balance_after_cents'])
    return entry


@transaction.atomic
def donate(*, donor, artist, amount_cents, operation_key):
    if donor.pk == artist.user_id:
        raise ValidationError('Нельзя поддержать самого себя.')
    if amount_cents <= 0 or artist.moderation_status != 'approved' or not artist.user.is_active:
        raise ValidationError('Операция недоступна.')
    donation, created = Donation.objects.get_or_create(
        idempotency_key=operation_key,
        defaults={'donor': donor, 'artist': artist, 'amount_cents': amount_cents},
    )
    if not created:
        if (
            donation.donor_id,
            donation.artist_id,
            donation.amount_cents
        ) != (donor.pk, artist.pk, amount_cents):
            raise ValidationError('Параметры операции не совпадают с подтверждёнными.')
        return donation
    adjust_balance(
        user=donor,
        amount_cents=-amount_cents,
        operation_key=f'{operation_key}:out',
        description=f'Поддержка {artist.user.username}'
    )
    adjust_balance(
        user=artist.user,
        amount_cents=amount_cents,
        operation_key=f'{operation_key}:in',
        description=f'Поддержка от {donor.username}'
    )
    return donation
