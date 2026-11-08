from django.db import migrations


def encrypt_existing(apps, schema_editor):
    from accounts import totp

    User = apps.get_model("accounts", "User")
    for user in User.objects.exclude(totp_secret="").iterator():
        if not user.totp_secret.startswith("enc1:"):
            user.totp_secret = totp.encrypt_secret(user.totp_secret)
            user.save(update_fields=["totp_secret"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_totp_encryption_and_replay")]

    # Not reversible on purpose: decrypting would put second-factor secrets back in plaintext.
    operations = [migrations.RunPython(encrypt_existing, migrations.RunPython.noop)]
