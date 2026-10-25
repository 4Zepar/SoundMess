from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pc_store.forms import BalanceAdjustmentForm, ModerationCommentFilterForm, ReviewForm
from pc_store.models import Album, Artist, Comment, ModerationAction, Track
from pc_store.permissions import administrator_required, moderator_required
from pc_store.selectors import track_cards
from pc_store.services.payments import adjust_balance
from pc_store.services.publication import review_content
from pc_store.views.wallet import payment_token, read_payment_token


@moderator_required
def dashboard(request):
    return render(request, 'moderation/dashboard.html', {
        'pending_artists_count': Artist.objects.filter(moderation_status='pending').count(),
        'pending_tracks_count': Track.objects.filter(moderation_status='pending').count(),
        'pending_albums_count': Album.objects.filter(is_public=True, moderation_status='pending').count(),
        'actions': ModerationAction.objects.select_related('actor')[:20],
    })


@moderator_required
def applications(request):
    status = request.GET.get('status', 'pending')
    query = Artist.objects.select_related('user__profile')
    if status in {'pending', 'approved', 'rejected'}:
        query = query.filter(moderation_status=status)
    page = Paginator(query.order_by('-user__date_joined'), 20).get_page(request.GET.get('page'))
    return render(
        request,
        'moderation/applications.html',
        {'applications': page.object_list, 'page_obj': page, 'status': status}
    )


@moderator_required
@require_POST
def review_application(request, artist_id):
    artist = get_object_or_404(Artist, pk=artist_id)
    form = ReviewForm(request.POST)
    if not form.is_valid() or form.cleaned_data['decision'] not in {'approved', 'rejected'}:
        messages.error(request, 'Выберите решение и укажите причину отклонения.')
        return redirect('moderation_applications')
    if artist.user_id == request.user.pk:
        raise PermissionDenied
    with transaction.atomic():
        artist = Artist.objects.select_for_update().get(pk=artist.pk)
        if artist.moderation_status != 'pending':
            messages.error(request, 'Эта заявка уже рассмотрена.')
            return redirect('moderation_applications')
        artist.moderation_status = form.cleaned_data['decision']
        artist.moderation_note = form.cleaned_data['note']
        artist.reviewed_at = timezone.now()
        artist.save(update_fields=['moderation_status', 'moderation_note', 'reviewed_at'])
        if artist.moderation_status == 'approved':
            artist.user.profile.role = 'artist'
            artist.user.profile.save(update_fields=['role'])
        ModerationAction.objects.create(
            actor=request.user,
            target_type='artist',
            target_id=artist.pk,
            action=artist.moderation_status,
            note=artist.moderation_note
        )
    messages.success(request, 'Решение по заявке сохранено.')
    return redirect('moderation_applications')


@moderator_required
def content_queue(request, kind):
    model = Track if kind == 'track' else Album
    query = model.objects.all()
    query = query.select_related(
        'artist__user'
    ) if kind == 'track' else query.filter(is_public=True).select_related('owner')
    status = request.GET.get('status', 'pending')
    if status in {'draft', 'pending', 'approved', 'rejected', 'hidden'}:
        query = query.filter(moderation_status=status)
    search = request.GET.get('q', '')[:200].strip()
    if search:
        owner = 'artist__user__username__icontains' if kind == 'track' else 'owner__username__icontains'
        query = query.filter(Q(title__icontains=search) | Q(**{owner: search}))
    page = Paginator(query.order_by('-created_at', '-pk'), 20).get_page(request.GET.get('page'))
    return render(
        request,
        'moderation/content.html',
        {
            'items': page.object_list,
            'page_obj': page,
            'kind': kind,
            'status': status,
            'search': search
        }
    )


@moderator_required
@require_POST
def review_material(request, kind, object_id):
    model = Track if kind == 'track' else Album
    item = get_object_or_404(model, pk=object_id)
    form = ReviewForm(request.POST)
    if form.is_valid():
        try:
            review_content(
                item,
                actor=request.user,
                decision=form.cleaned_data['decision'],
                note=form.cleaned_data['note']
            )
            messages.success(request, 'Решение сохранено.')
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
    else:
        messages.error(request, 'Укажите корректное решение и причину.')
    return redirect('moderation_tracks' if kind == 'track' else 'moderation_albums')


@moderator_required
def comments(request):
    form = ModerationCommentFilterForm(request.GET)
    albums = Album.objects.filter(
        tracks=OuterRef('pk'), owner_id=OuterRef('artist__user_id'),
        is_public=True, is_favorite_folder=False,
    ).exclude(release_type='single')
    tracks = Track.objects.select_related('artist__user').annotate(
        comment_count=Count('comments', distinct=True),
        hidden_comment_count=Count('comments', filter=Q(comments__is_hidden=True), distinct=True),
        last_comment_at=Max('comments__created_at'),
        has_album=Exists(albums),
    ).filter(comment_count__gt=0)
    if form.is_valid():
        data = form.cleaned_data
        if data['q']:
            tracks = tracks.filter(
                Q(title__icontains=data['q']) | Q(artist__user__username__icontains=data['q']),
            )
        if data['artist']:
            tracks = tracks.filter(artist=data['artist'])
        if data['release_kind']:
            tracks = tracks.filter(has_album=data['release_kind'] == 'album')
    else:
        tracks = tracks.none()
    page = Paginator(tracks.order_by('-last_comment_at', '-pk'), 24).get_page(request.GET.get('page'))
    detail_query = request.GET.copy()
    detail_query.pop('page', None)
    detail_query['list_page'] = page.number
    return render(request, 'moderation/comments.html', {
        'filter_form': form, 'tracks': page.object_list, 'page_obj': page,
        'detail_query': detail_query.urlencode(),
    })


@moderator_required
def track_comments(request, track_id):
    track = get_object_or_404(track_cards(request.user, Track.objects.all()), pk=track_id)
    query = track.comments.filter(parent__isnull=True).select_related('author').order_by('-created_at', '-pk')
    page = Paginator(query, 30).get_page(request.GET.get('page'))
    roots = list(page.object_list)
    comments = list(roots)
    for comment in roots:
        comment.depth = 0
        comment.hidden_by_parent = False
        comment.moderation_replies = []
    # Fetch one level at a time so complete threads stay together without N+1 queries.
    level = roots
    while level:
        parents = {comment.pk: comment for comment in level}
        replies = list(track.comments.filter(parent_id__in=parents).select_related('author').order_by('created_at', 'pk'))
        for reply in replies:
            parent = parents[reply.parent_id]
            reply.parent = parent
            reply.depth = parent.depth + 1
            reply.hidden_by_parent = parent.is_hidden or parent.hidden_by_parent
            reply.moderation_replies = []
            parent.moderation_replies.append(reply)
        comments.extend(replies)
        level = replies
    for comment in reversed(comments):
        comment.descendant_count = sum(1 + reply.descendant_count for reply in comment.moderation_replies)
    back_query = request.GET.copy()
    list_page = back_query.pop('list_page', None)
    back_query.pop('page', None)
    if list_page:
        back_query['page'] = list_page[-1]
    return render(request, 'moderation/track_comments.html', {
        'track': track, 'comments': comments, 'comment_threads': roots, 'page_obj': page,
        'comment_count': track.comments.count(), 'thread_count': page.paginator.count,
        'back_query': back_query.urlencode(),
    })


@moderator_required
@require_POST
def comment_visibility(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    hidden = request.POST.get('hidden') == 'true'
    with transaction.atomic():
        comment.is_hidden = hidden
        comment.save(update_fields=['is_hidden'])
        ModerationAction.objects.create(
            actor=request.user,
            target_type='comment',
            target_id=comment.pk,
            action='hidden' if hidden else 'restored'
        )
    messages.success(request, 'Видимость комментария изменена.')
    destination = reverse('moderation_track_comments', args=[comment.track_id])
    if request.GET:
        destination += '?' + request.GET.urlencode()
    return redirect(destination)


@moderator_required
@require_POST
def delete_comment(request, comment_id):
    with transaction.atomic():
        comment = get_object_or_404(
            Comment.objects.select_for_update().select_related('author', 'track'), pk=comment_id,
        )
        track_id = comment.track_id
        author = comment.author.username
        track_title = comment.track.title
        _, deleted = comment.delete()
        count = deleted.get(Comment._meta.label, 0)
        ModerationAction.objects.create(
            actor=request.user, target_type='comment', target_id=comment_id, action='deleted',
            note=f'Автор: {author}. Трек: {track_title}. Удалено комментариев вместе с ответами: {count}.',
        )
    messages.success(request, 'Комментарий и ответы удалены.' if count > 1 else 'Комментарий удалён.')
    destination = reverse('moderation_track_comments', args=[track_id])
    if request.GET:
        destination += '?' + request.GET.urlencode()
    return redirect(destination)


@administrator_required
def users(request):
    query = get_user_model().objects.select_related('profile', 'artist', 'wallet').order_by('username')
    search = request.GET.get('q', '')[:200].strip()
    if search:
        query = query.filter(Q(username__icontains=search) | Q(email__icontains=search))
    page = Paginator(query, 30).get_page(request.GET.get('page'))
    return render(
        request,
        'moderation/users.html',
        {'users': page.object_list, 'page_obj': page, 'search': search}
    )


@administrator_required
def user_detail(request, user_id):
    account = get_object_or_404(get_user_model().objects.select_related('profile', 'wallet'), pk=user_id)
    role = 'administrator' if account.is_superuser or account.groups.filter(
        name='Администраторы'
    ).exists() else 'moderator' if account.groups.filter(name='Модераторы').exists() else 'member'
    return render(request, 'moderation/user_detail.html', {
        'account': account, 'account_role': role,
        'tracks': track_cards(request.user, Track.objects.filter(artist__user=account)),
        'albums': account.albums.filter(is_public=True),
        'comments': account.track_comments.select_related('track')[:20],
        'wallet': account.wallet,
        'adjustment_form': BalanceAdjustmentForm(
            initial={'token': payment_token(request.user, f'adjust:{account.pk}')}
        ),
        'transactions': account.wallet.transactions.all()[:15],
    })


@administrator_required
@require_POST
def adjust_user_balance(request, user_id):
    account = get_object_or_404(get_user_model(), pk=user_id)
    form = BalanceAdjustmentForm(request.POST)
    if form.is_valid():
        try:
            claims = read_payment_token(form.cleaned_data['token'], request.user, f'adjust:{account.pk}')
            with transaction.atomic():
                entry = adjust_balance(
                    user=account,
                    amount_cents=int(form.cleaned_data['amount'] * 100),
                    operation_key=claims['nonce'],
                    description=form.cleaned_data['note']
                )
                ModerationAction.objects.get_or_create(
                    actor=request.user,
                    target_type='wallet_transaction',
                    target_id=entry.pk,
                    action='balance_adjustment',
                    defaults={'note': form.cleaned_data['note']}
                )
            messages.success(request, 'Баланс изменён.')
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
    else:
        messages.error(request, 'Проверьте сумму и причину изменения.')
    return redirect('moderation_user_detail', user_id=account.pk)


@administrator_required
@require_POST
def update_user(request, user_id):
    account = get_object_or_404(get_user_model(), pk=user_id)
    if account.pk == request.user.pk or (account.is_superuser and not request.user.is_superuser):
        raise PermissionDenied
    with transaction.atomic():
        action = request.POST.get('action')
        if action == 'active' and request.POST.get('active') in {'true', 'false'}:
            if account.is_superuser:
                raise PermissionDenied
            account.is_active = request.POST['active'] == 'true'
            account.save(update_fields=['is_active'])
            note = 'Аккаунт активирован' if account.is_active else 'Аккаунт заблокирован'
        elif action == 'role' and request.POST.get('role') in {'member', 'moderator', 'administrator'}:
            if account.is_superuser:
                raise PermissionDenied
            role = request.POST['role']
            account.groups.remove(*Group.objects.filter(name__in=['Модераторы', 'Администраторы']))
            if role != 'member':
                account.groups.add(
                    Group.objects.get(name='Администраторы' if role == 'administrator' else 'Модераторы')
                )
            account.is_staff = role != 'member'
            account.save(update_fields=['is_staff'])
            labels = {'member': 'Пользователь', 'moderator': 'Модератор', 'administrator': 'Администратор'}
            note = f'Уровень доступа сохранён: {labels[role]}.'
        else:
            messages.error(request, 'Некорректное действие.')
            return redirect('moderation_user_detail', user_id=account.pk)
        ModerationAction.objects.create(
            actor=request.user,
            target_type='user',
            target_id=account.pk,
            action=action,
            note=note
        )
    messages.success(request, note)
    return redirect('moderation_user_detail', user_id=account.pk)
