import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class Role(models.Model):
    ROLE_CHOICES = [
        ('System_Admin',       'System Administrator'),
        ('DRRMO_Officer',      'DRRMO Officer'),
        ('Barangay_Personnel', 'Barangay Personnel'),
    ]
    name        = models.CharField(max_length=40, choices=ROLE_CHOICES, unique=True)
    description = models.TextField(blank=True)

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
    id                 = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role               = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    full_name          = models.CharField(max_length=150)
    email              = models.EmailField(unique=True)
    failed_login_count = models.IntegerField(default=0)
    locked_until       = models.DateTimeField(null=True, blank=True)
    is_active          = models.BooleanField(default=True)
    is_staff           = models.BooleanField(default=False)
    created_at         = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        db_table = 'user'

    def __str__(self):
        return f'{self.full_name} ({self.email})'

    def is_locked(self):
        from django.utils import timezone
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False