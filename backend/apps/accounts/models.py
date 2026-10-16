import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class Role(models.Model):
    ROLE_CHOICES = [
        ('System_Admin',       'System Administrator'),
        ('DRRMO_Officer',      'DRRMO Officer'),
        ('Barangay_Personnel', 'Barangay Personnel'),
    ]
    id          = models.BigAutoField(primary_key=True, db_column='role_id')
    name        = models.CharField(max_length=40, choices=ROLE_CHOICES, unique=True, db_column='role_name')
    description = models.TextField(blank=True, db_column='role_desc')

    class Meta:
        db_table = 'role'

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='user_id')
    role                = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, db_column='user_role_id')
    full_name           = models.CharField(max_length=150, db_column='user_full_name')
    email               = models.EmailField(unique=True, db_column='user_email')

    # Personnel profile. full_name above stays the display name used across
    # the app (reports, logs, navbar) and is rebuilt from these parts
    # whenever they're set. All nullable so accounts created before these
    # fields existed (and teammates' branches without them) keep working.
    first_name          = models.CharField(max_length=60, null=True, blank=True, db_column='user_first_name')
    middle_initial      = models.CharField(max_length=3, null=True, blank=True, db_column='user_middle_initial')
    last_name           = models.CharField(max_length=60, null=True, blank=True, db_column='user_last_name')
    suffix              = models.CharField(max_length=10, null=True, blank=True, db_column='user_suffix')
    phone               = models.CharField(max_length=20, null=True, blank=True, db_column='user_phone')
    employee_id         = models.CharField(max_length=30, null=True, blank=True, db_column='user_employee_id')
    position            = models.CharField(max_length=100, null=True, blank=True, db_column='user_position')
    assigned_barangay   = models.ForeignKey(
        'barangays.Barangay', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='personnel', db_column='user_brgy_id',
    )

    failed_login_count  = models.IntegerField(default=0, db_column='user_failed_login_count')
    locked_until        = models.DateTimeField(null=True, blank=True, db_column='user_locked_until')
    is_active           = models.BooleanField(default=True, db_column='user_is_active')
    is_staff            = models.BooleanField(default=False, db_column='user_is_staff')
    created_at          = models.DateTimeField(auto_now_add=True, db_column='user_created_at')

    # Fields inherited from Django's base classes, redefined only to rename the columns
    password     = models.CharField(max_length=128, db_column='user_password_hash')
    last_login   = models.DateTimeField(null=True, blank=True, db_column='user_last_login')
    is_superuser = models.BooleanField(default=False, db_column='user_is_superuser')

    # Two-factor authentication (Google Authenticator / any TOTP app)
    two_factor_enabled  = models.BooleanField(default=False, db_column='user_two_factor_enabled')
    two_factor_secret   = models.CharField(max_length=32, blank=True, null=True, db_column='user_two_factor_secret')

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        db_table = 'app_user'

    def __str__(self):
        return f'{self.full_name} ({self.email})'

    def compose_full_name(self):
        """'Juan D. Dela Cruz Jr.' from the name parts, or '' if there are none."""
        middle = f'{self.middle_initial}.' if self.middle_initial else ''
        parts = [self.first_name, middle, self.last_name, self.suffix]
        return ' '.join(p.strip() for p in parts if p and p.strip())

    def is_locked(self):
        from django.utils import timezone
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False