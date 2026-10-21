from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from pc_store.forms import PaymentForm
from pc_store.models import Artist
from pc_store.services.payments import adjust_balance, donate

PAYMENT_SALT = 'soundmess.payment'


def payment_token(user, purpose, **claims):
    return signing.dumps(
        {'user': user.pk, 'purpose': purpose, 'nonce': uuid4().hex, **claims},
        salt=PAYMENT_SALT
    )


def read_payment_token(token, user, purpose):
    try:
        claims = signing.loads(token, salt=PAYMENT_SALT, max_age=1800)
    except signing.BadSignature as error:
        raise ValidationError('Подтверждение устарело. Обновите страницу и повторите операцию.') from error
    if claims.get('user') != user.pk or claims.get('purpose') != purpose:
        raise ValidationError('Некорректное подтверждение операции.')
    return claims


def payment_page(request, artist=None):
    purpose = f'donation:{artist.pk}' if artist else 'topup'
    form = PaymentForm(request.POST or None, initial={'token': payment_token(request.user, purpose)})
    confirmation = False
    if request.method == 'POST' and form.is_valid():
        amount = form.cleaned_data['amount']
        cents = int(amount * 100)
        try:
            claims = read_payment_token(form.cleaned_data['token'], request.user, purpose)
            if artist and artist.user_id == request.user.pk:
                raise ValidationError('Нельзя поддержать самого себя.')
            if artist and request.user.wallet.balance_cents < cents and not request.POST.get('confirm'):
                raise ValidationError('Недостаточно средств на балансе.')
            if request.POST.get('confirm') == 'yes':
                if claims.get('amount') != cents:
                    raise ValidationError('Сумма отличается от подтверждённой.')
                if artist:
                    donate(
                        donor=request.user,
                        artist=artist,
                        amount_cents=cents,
                        operation_key=claims['nonce']
                    )
                else:
                    adjust_balance(
                        user=request.user,
                        amount_cents=cents,
                        operation_key=claims['nonce'],
                        description='Демонстрационное пополнение'
                    )
                messages.success(
                    request,
                    'Поддержка отправлена. Спасибо!' if artist else 'Демонстрационный баланс пополнен.'
                )
                return redirect(
                    'support_artist',
                    artist_id=artist.pk
                ) if artist else redirect('wallet_top_up')
            claims['amount'] = cents
            confirmed_token = signing.dumps(claims, salt=PAYMENT_SALT)
            form = PaymentForm(initial={'amount': amount, 'token': confirmed_token})
            confirmation = True
        except ValidationError as error:
            form.add_error(None, error)
    return render(request, 'support_artist.html' if artist else 'wallet_top_up.html', {
        'form': form, 'artist': artist, 'confirmation': confirmation,
        'confirmation_amount': form['amount'].value(), 'wallet': request.user.wallet,
        'transactions': request.user.wallet.transactions.all()[:30],
        'donations': request.user.donations_sent.filter(artist=artist)[:10] if artist else [],
    })


@login_required
def wallet_top_up(request):
    return payment_page(request)


@login_required
def support_artist(request, artist_id):
    artist = get_object_or_404(
        Artist.objects.select_related('user'),
        pk=artist_id,
        moderation_status='approved',
        user__is_active=True
    )
    return payment_page(request, artist)
