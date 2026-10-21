from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pc_store', '0004_album_cover'),
    ]

    operations = [
        migrations.RenameField(
            model_name='track',
            old_name='plays',
            new_name='plays_count',
        ),
        migrations.AddField(
            model_name='artist',
            name='moderation_note',
            field=models.TextField(blank=True, verbose_name='Комментарий модератора'),
        ),
        migrations.AddField(
            model_name='artist',
            name='moderation_status',
            field=models.CharField(choices=[('pending', 'На модерации'), ('approved', 'Одобрен'), ('rejected', 'Отклонён')], default='pending', max_length=10, verbose_name='Статус модерации'),
        ),
        migrations.AddField(
            model_name='artist',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Дата проверки'),
        ),
        migrations.AddField(
            model_name='track',
            name='duration_seconds',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Длительность, секунд'),
        ),
        migrations.AddField(
            model_name='track',
            name='is_explicit',
            field=models.BooleanField(default=False, verbose_name='Без цензуры'),
        ),
        migrations.AddField(
            model_name='track',
            name='lyrics',
            field=models.TextField(blank=True, verbose_name='Текст песни'),
        ),
        migrations.AddField(
            model_name='track',
            name='mood',
            field=models.CharField(blank=True, max_length=50, verbose_name='Настроение'),
        ),
        migrations.AddField(
            model_name='track',
            name='release_type',
            field=models.CharField(choices=[('single', 'Сингл'), ('album', 'Альбом'), ('ep', 'EP'), ('mixtape', 'Микстейп')], default='single', max_length=10, verbose_name='Тип релиза'),
        ),
        migrations.AddField(
            model_name='track',
            name='release_year',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Год выпуска'),
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(max_length=1000)),
                ('timestamp_seconds', models.PositiveIntegerField(default=0, verbose_name='Таймкод, секунд')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_hidden', models.BooleanField(default=False, verbose_name='Скрыт модератором')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='track_comments', to='auth.user')),
                ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='pc_store.track')),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.CreateModel(
            name='Follow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('artist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='followers', to='pc_store.artist')),
                ('follower', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='artist_follows', to='auth.user')),
            ],
            options={'ordering': ['-created_at'], 'constraints': [models.UniqueConstraint(fields=('follower', 'artist'), name='unique_artist_follow')]},
        ),
    ]