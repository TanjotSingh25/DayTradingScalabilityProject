# Generated by Django 5.1.5 on 2025-02-02 06:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_rename_user_users'),
    ]

    operations = [
        migrations.RenameField(
            model_name='users',
            old_name='username',
            new_name='user_name',
        ),
    ]
