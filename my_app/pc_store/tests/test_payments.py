from django.core.exceptions import ValidationError
from django.urls import reverse
from unittest.mock import patch

from pc_store.models import Donation, Wallet, WalletTransaction
from pc_store.services.payments import adjust_balance, donate
from pc_store.views.wallet import payment_token
from .base import AppTestCase


class PaymentTests(AppTestCase):
    def setUp(self):
        super().setUp()
        adjust_balance(
            user=self.listener,
            amount_cents=1000,
            operation_key='initial',
            description='Test opening'
        )

    def test_donation_moves_funds_and_creates_matching_ledger(self):
        donation = donate(
            donor=self.listener,
            artist=self.artist,
            amount_cents=500,
            operation_key='donation-1'
        )
        self.assertEqual(donation.amount_cents, 500)
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 500)
        self.assertEqual(Wallet.objects.get(user=self.artist_user).balance_cents, 500)
        entries = list(donation.transactions.order_by('amount_cents'))
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            [(entry.wallet.user_id, entry.type, entry.amount_cents, entry.balance_after_cents) for entry in entries],
            [(self.listener.pk, 'donation_out', -500, 500), (self.artist_user.pk, 'donation_in', 500, 500)],
        )
        self.assertEqual(
            sum(
                WalletTransaction.objects.filter(
                    wallet__user=self.listener
                ).values_list('amount_cents', flat=True)
            ),
            500
        )

    def test_repeated_confirmation_never_charges_twice(self):
        for _ in range(2):
            donate(
                donor=self.listener,
                artist=self.artist,
                amount_cents=500,
                operation_key='same-confirmation'
            )
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 500)
        self.assertEqual(Donation.objects.get().transactions.count(), 2)

    def test_insufficient_balance_rolls_back_entire_transfer(self):
        with self.assertRaises(ValidationError):
            donate(donor=self.listener, artist=self.artist, amount_cents=2000, operation_key='not-enough')
        self.assertFalse(Donation.objects.exists())
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1000)
        self.assertEqual(Wallet.objects.get(user=self.artist_user).balance_cents, 0)

    def test_self_donation_is_rejected(self):
        with self.assertRaises(ValidationError):
            donate(donor=self.artist_user, artist=self.artist, amount_cents=1, operation_key='self')

    def test_topup_requires_confirmation_and_is_idempotent(self):
        self.login()
        url = reverse('wallet_top_up')
        initial = payment_token(self.listener, 'topup')
        preview = self.client.post(url, {'amount': '5.00', 'token': initial})
        self.assertTrue(preview.context['confirmation'])
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1000)
        confirmed = preview.context['form']['token'].value()
        payload = {'amount': '5.00', 'token': confirmed, 'confirm': 'yes'}
        for _ in range(2):
            self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1500)

    def test_confirmation_token_is_bound_to_amount(self):
        self.login()
        url = reverse('wallet_top_up')
        response = self.client.post(url, {'amount': '5.00', 'token': payment_token(self.listener, 'topup')})
        token = response.context['form']['token'].value()
        response = self.client.post(url, {'amount': '50.00', 'token': token, 'confirm': 'yes'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Сумма отличается')
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1000)

    def test_confirmation_token_is_bound_to_user(self):
        self.login()
        response = self.client.post(
            reverse('wallet_top_up'),
            {'amount': '5.00', 'token': payment_token(self.artist_user, 'topup')}
        )
        self.assertContains(response, 'Некорректное подтверждение')
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1000)

    def test_balance_adjustment_is_also_idempotent(self):
        for _ in range(2):
            adjust_balance(
                user=self.listener,
                amount_cents=100,
                operation_key='adjust',
                description='Adjustment'
            )
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1100)

    def test_topup_and_withdrawal_have_explicit_types(self):
        entry = adjust_balance(user=self.listener, amount_cents=-100, operation_key='withdraw', description='Adjustment')
        self.assertEqual(entry.type, WalletTransaction.Type.WITHDRAWAL)
        self.assertIsNone(entry.donation_id)
        self.assertEqual(WalletTransaction.objects.get(operation_key='initial').type, WalletTransaction.Type.TOPUP)

    def test_failed_recipient_entry_rolls_back_donation_both_balances_and_ledger(self):
        original_create = WalletTransaction.objects.create

        def fail_incoming(**kwargs):
            if kwargs['type'] == WalletTransaction.Type.DONATION_IN:
                raise RuntimeError('Incoming ledger failure')
            return original_create(**kwargs)

        with patch.object(WalletTransaction.objects, 'create', side_effect=fail_incoming):
            with self.assertRaisesMessage(RuntimeError, 'Incoming ledger failure'):
                donate(donor=self.listener, artist=self.artist, amount_cents=100, operation_key='rollback')
        self.assertFalse(Donation.objects.exists())
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 1000)
        self.assertEqual(Wallet.objects.get(user=self.artist_user).balance_cents, 0)
        self.assertEqual(WalletTransaction.objects.count(), 1)

    def test_same_key_from_two_donors_does_not_collide_in_artist_wallet(self):
        adjust_balance(user=self.moderator, amount_cents=1000, operation_key='initial', description='Topup')
        donations = [donate(donor=donor, artist=self.artist, amount_cents=100, operation_key='shared')
                     for donor in (self.listener, self.moderator)]
        self.assertEqual(len({donation.pk for donation in donations}), 2)
        self.assertEqual(Wallet.objects.get(user=self.artist_user).balance_cents, 200)
        self.assertTrue(all(donation.transactions.count() == 2 for donation in donations))

    def test_reusing_a_key_with_changed_parameters_is_rejected(self):
        donate(donor=self.listener, artist=self.artist, amount_cents=100, operation_key='bound')
        with self.assertRaises(ValidationError):
            donate(donor=self.listener, artist=self.artist, amount_cents=200, operation_key='bound')
        with self.assertRaises(ValidationError):
            adjust_balance(user=self.listener, amount_cents=2000, operation_key='initial', description='Tampered')
        self.assertEqual(Wallet.objects.get(user=self.listener).balance_cents, 900)
        self.assertEqual(Donation.objects.count(), 1)
