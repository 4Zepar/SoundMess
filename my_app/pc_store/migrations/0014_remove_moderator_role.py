from django.db import migrations
from django.db.models import Q


def remove_moderator_role(apps, schema_editor):
    alias = schema_editor.connection.alias
    users = apps.get_model('auth', 'User').objects.using(alias)
    groups = apps.get_model('auth', 'Group').objects.using(alias)
    permissions = apps.get_model('auth', 'Permission').objects.using(alias)

    moderators = groups.filter(name='Модераторы')
    obsolete_permission = permissions.filter(
        content_type__app_label='pc_store',
        content_type__model='moderationaction',
        codename='moderate_content',
    )
    former_moderators = users.filter(is_staff=True, is_superuser=False).filter(
        Q(groups__in=moderators)
        | Q(user_permissions__in=obsolete_permission)
        | Q(groups__permissions__in=obsolete_permission)
    )
    other_permissions = permissions.exclude(pk__in=obsolete_permission)
    other_groups = groups.exclude(pk__in=moderators).filter(permissions__in=other_permissions)
    staff_with_other_permissions = users.filter(
        Q(user_permissions__in=other_permissions) | Q(groups__in=other_groups)
    )
    former_moderators.exclude(pk__in=staff_with_other_permissions.values('pk')).update(is_staff=False)

    moderators.delete()
    obsolete_permission.delete()


class Migration(migrations.Migration):
    dependencies = [('pc_store', '0013_database_integrity')]
    operations = [
        migrations.AlterModelOptions(
            name='moderationaction',
            options={
                'ordering': ['-created_at', '-pk'],
                'permissions': [('manage_accounts', 'Управление пользователями и балансами')],
            },
        ),
        migrations.RunPython(remove_moderator_role, migrations.RunPython.noop),
    ]
