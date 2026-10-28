from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from pc_store.models import Donation, Wallet, WalletTransaction


def _lock_wallets(*users):
    user_ids = sorted({user.pk for user in users})
    if connection.vendor == 'sqlite':
        # SQLite has no row locks; acquire its write reservation before reading balances.
        Wallet.objects.filter(user_id__in=user_ids).update(balance_cents=F('balance_cents'))
    for user_id in user_ids:
        Wallet.objects.get_or_create(user_id=user_id)
    return {
        wallet.user_id: wallet
        for wallet in Wallet.objects.select_for_update().filter(user_id__in=user_ids).order_by('pk')
    }


def _change_balance(wallet, amount_cents):
    query = Wallet.objects.filter(pk=wallet.pk)
    if amount_cents < 0:
        query = query.filter(balance_cents__gte=-amount_cents)
    if not query.update(balance_cents=F('balance_cents') + amount_cents, updated_at=timezone.now()):
        raise ValidationError('Недостаточно средств на балансе.')
    wallet.refresh_from_db()


def _record_change(wallet, *, amount_cents, operation_key, description, entry_type, donation=None):
    entry = WalletTransaction.objects.filter(wallet=wallet, operation_key=operation_key).first()
    if entry:
        if (entry.amount_cents, entry.type, entry.donation_id) != (
            amount_cents, entry_type, donation.pk if donation else None,
        ):
            raise ValidationError('Параметры операции не совпадают с подтверждёнными.')
        return entry
    _change_balance(wallet, amount_cents)
    return WalletTransaction.objects.create(
        wallet=wallet, amount_cents=amount_cents, balance_after_cents=wallet.balance_cents,
        operation_key=operation_key, description=description, type=entry_type, donation=donation,
    )


def _validate_key(key, max_length):
    if not isinstance(key, str) or not key.strip() or len(key) > max_length:
        raise ValidationError('Некорректный ключ операции.')


@transaction.atomic
def adjust_balance(*, user, amount_cents, operation_key, description):
    if not amount_cents:
        raise ValidationError('Сумма должна отличаться от нуля.')
    _validate_key(operation_key, 100)
    wallet = _lock_wallets(user)[user.pk]
    return _record_change(
        wallet, amount_cents=amount_cents, operation_key=operation_key, description=description,
        entry_type=WalletTransaction.Type.TOPUP if amount_cents > 0 else WalletTransaction.Type.WITHDRAWAL,
    )


@transaction.atomic
def donate(*, donor, artist, amount_cents, operation_key):
    if donor.pk == artist.user_id:
        raise ValidationError('Нельзя поддержать самого себя.')
    if amount_cents <= 0 or artist.moderation_status != 'approved' or not artist.user.is_active:
        raise ValidationError('Операция недоступна.')
    _validate_key(operation_key, 64)
    wallets = _lock_wallets(donor, artist.user)
    donation, created = Donation.objects.get_or_create(
        donor=donor, idempotency_key=operation_key,
        defaults={'artist': artist, 'amount_cents': amount_cents},
    )
    if not created:
        if (
            donation.donor_id,
            donation.artist_id,
            donation.amount_cents
        ) != (donor.pk, artist.pk, amount_cents):
            raise ValidationError('Параметры операции не совпадают с подтверждёнными.')
        return donation
    ledger_key = f'donation:{donor.pk}:{operation_key}'
    _record_change(
        wallets[donor.pk],
        amount_cents=-amount_cents,
        operation_key=f'{ledger_key}:out',
        description=f'Поддержка {artist.user.username}',
        entry_type=WalletTransaction.Type.DONATION_OUT, donation=donation,
    )
    _record_change(
        wallets[artist.user_id],
        amount_cents=amount_cents,
        operation_key=f'{ledger_key}:in',
        description=f'Поддержка от {donor.username}',
        entry_type=WalletTransaction.Type.DONATION_IN, donation=donation,
    )
    return donation
