import re
import secrets
import string

from rest_framework import serializers

from apps.accounts.models import User, Role
from apps.barangays.models import Barangay
from apps.admin_dashboard.models import AuditLog


BARANGAY_ROLE = 'Barangay_Personnel'
SUFFIXES = ['Jr.', 'Sr.', 'II', 'III', 'IV', 'V']


def generate_temp_password(length=12):
    alphabet = string.ascii_letters + string.digits + '!@#'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def normalize_ph_mobile(value):
    """Accepts 09171234567, 9171234567, +639171234567 or 63 917 123 4567
    and stores it as +639171234567."""
    digits = re.sub(r'\D', '', value)
    if digits.startswith('63'):
        digits = digits[2:]
    elif digits.startswith('0'):
        digits = digits[1:]
    if not re.fullmatch(r'9\d{9}', digits):
        raise serializers.ValidationError(
            'Enter a valid Philippine mobile number, e.g. 0917 123 4567.'
        )
    return f'+63{digits}'


def clean_text(value):
    """Trim and collapse inner spaces; empty becomes None."""
    if value is None:
        return None
    value = ' '.join(value.split())
    return value or None


class RolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'description']


class BarangayOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Barangay
        fields = ['id', 'name']


class UserListSerializer(serializers.ModelSerializer):
    role = RolesSerializer(read_only=True)
    assigned_barangay = BarangayOptionSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'first_name', 'middle_initial', 'last_name', 'suffix',
            'email', 'phone', 'employee_id', 'position',
            'role', 'assigned_barangay', 'is_active', 'last_login', 'created_at',
        ]


class UserWriteSerializer(serializers.ModelSerializer):
    """Shared validation for creating and editing accounts."""

    # Declared explicitly so DRF doesn't add its own case-sensitive unique
    # check; validate_email does a case-insensitive one instead.
    email = serializers.EmailField(max_length=254)
    role_id = serializers.IntegerField(write_only=True)
    assigned_barangay_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    first_name = serializers.CharField(max_length=60, required=False, allow_blank=True, allow_null=True)
    middle_initial = serializers.CharField(max_length=3, required=False, allow_blank=True, allow_null=True)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True, allow_null=True)
    suffix = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True)
    employee_id = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    position = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    # Older clients still send a single full_name; accepted when no name parts are given.
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'first_name', 'middle_initial', 'last_name', 'suffix',
            'email', 'phone', 'employee_id', 'position',
            'role_id', 'assigned_barangay_id',
        ]

    # ---- field-level ----

    def validate_first_name(self, value):
        return clean_text(value)

    def validate_last_name(self, value):
        return clean_text(value)

    def validate_position(self, value):
        return clean_text(value)

    def validate_middle_initial(self, value):
        value = (value or '').replace('.', '').strip()
        if not value:
            return None
        if not re.fullmatch(r'[A-Za-zÑñ]{1,2}', value):
            raise serializers.ValidationError('Use one or two letters, e.g. "D".')
        return value.upper()

    def validate_suffix(self, value):
        value = clean_text(value)
        if value and value not in SUFFIXES:
            raise serializers.ValidationError(f'Choose one of: {", ".join(SUFFIXES)}.')
        return value

    def validate_phone(self, value):
        value = clean_text(value)
        return normalize_ph_mobile(value) if value else None

    def validate_email(self, value):
        value = value.strip().lower()
        others = User.objects.filter(email__iexact=value)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate_employee_id(self, value):
        value = clean_text(value)
        if not value:
            return None
        others = User.objects.filter(employee_id__iexact=value)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError('Another account already uses this employee ID.')
        return value

    def validate_role_id(self, value):
        if not Role.objects.filter(id=value).exists():
            raise serializers.ValidationError('Choose a valid role.')
        return value

    def validate_assigned_barangay_id(self, value):
        if value is not None and not Barangay.objects.filter(id=value).exists():
            raise serializers.ValidationError('Choose a valid barangay.')
        return value

    # ---- cross-field ----

    def validate(self, attrs):
        instance = self.instance
        errors = {}

        # Names: required on create (unless a legacy full_name is sent), and
        # can't be blanked out when edited.
        def current(field):
            if field in attrs:
                return attrs[field]
            return getattr(instance, field, None) if instance else None

        sends_name_parts = 'first_name' in attrs or 'last_name' in attrs
        legacy_only = not sends_name_parts and clean_text(attrs.get('full_name'))
        if (instance is None and not legacy_only) or (instance is not None and sends_name_parts):
            if not current('first_name'):
                errors['first_name'] = 'First name is required.'
            if not current('last_name'):
                errors['last_name'] = 'Last name is required.'

        # Barangay assignment: only checked when the role or barangay is being
        # set, so activating an older account doesn't fail on it.
        if 'role_id' in attrs or 'assigned_barangay_id' in attrs:
            role_id = attrs.get('role_id', instance.role_id if instance else None)
            role = Role.objects.filter(id=role_id).first()
            if role and role.name == BARANGAY_ROLE:
                barangay_id = (attrs['assigned_barangay_id'] if 'assigned_barangay_id' in attrs
                               else getattr(instance, 'assigned_barangay_id', None))
                if not barangay_id:
                    errors['assigned_barangay_id'] = 'Barangay personnel must be assigned to a barangay.'
            elif role:
                # Only barangay personnel belong to a single barangay
                attrs['assigned_barangay_id'] = None

        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class UserCreateSerializer(UserWriteSerializer):

    def create(self, validated_data):
        role = Role.objects.get(id=validated_data.pop('role_id'))
        barangay_id = validated_data.pop('assigned_barangay_id', None)
        legacy_name = clean_text(validated_data.pop('full_name', None))
        temp_password = generate_temp_password()

        user = User(
            role=role,
            assigned_barangay_id=barangay_id,
            **validated_data,
        )
        user.full_name = user.compose_full_name() or legacy_name or user.email
        user.set_password(temp_password)
        user.save()

        # Attach temp password to instance for the view to return
        user._temp_password = temp_password
        return user


class UserUpdateSerializer(UserWriteSerializer):
    role_id = serializers.IntegerField(write_only=True, required=False)
    email = serializers.EmailField(max_length=254, required=False)
    is_active = serializers.BooleanField(required=False)

    class Meta(UserWriteSerializer.Meta):
        fields = UserWriteSerializer.Meta.fields + ['is_active']

    def update(self, instance, validated_data):
        role_id = validated_data.pop('role_id', None)
        if role_id:
            instance.role = Role.objects.get(id=role_id)
        if 'assigned_barangay_id' in validated_data:
            instance.assigned_barangay_id = validated_data.pop('assigned_barangay_id')

        legacy_name = clean_text(validated_data.pop('full_name', None))
        for field, value in validated_data.items():
            setattr(instance, field, value)

        composed = instance.compose_full_name()
        if composed:
            instance.full_name = composed
        elif legacy_name:
            instance.full_name = legacy_name

        instance.save()
        return instance


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True, default=None)
    user_name = serializers.CharField(source='user.full_name', read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_email', 'user_name', 'action', 'target_table', 'target_id', 'details', 'ip_address', 'created_at']