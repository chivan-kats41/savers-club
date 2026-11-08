from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        """Look a user up by phone in ANY accepted spelling (canonical first, then rows stored the old way)."""
        from .phone import phone_variants

        variants = phone_variants(username)
        if variants:
            rows = {u.phone: u for u in self.filter(phone__in=variants)}
            for spelling in variants:
                if spelling in rows:
                    return rows[spelling]
            raise self.model.DoesNotExist
        return super().get_by_natural_key(username)

    def _create_user(self, phone, email, password, **extra_fields):
        if not phone:
            raise ValueError("Users must have a phone number.")
        email = str(email or "").strip().lower() or None     # one spelling, and NULL (not "") when blank: the column is unique
        user = self.model(phone=phone, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, email, password, **extra_fields)

    def create_superuser(self, phone, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "super_admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(phone, email, password, **extra_fields)
