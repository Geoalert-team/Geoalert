from rest_framework import serializers
from apps.accounts.models import User, Role


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'description']


class UserSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    # So the map can tell barangay personnel which answer on a hazard is
    # their own barangay's. Read-only: assignment is an admin action.
    assigned_barangay = serializers.PrimaryKeyRelatedField(read_only=True)
    # The id above is what the map compares answers against, so it stays an
    # id. Screens that need to *show* the barangay were reading
    # assigned_barangay.name off that number and silently getting undefined,
    # so the name is its own field rather than a change of shape.
    assigned_barangay_name = serializers.CharField(
        source='assigned_barangay.name', read_only=True, default=None,
    )

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'role', 'is_active', 'created_at', 'two_factor_enabled',
                  'assigned_barangay', 'assigned_barangay_name', 'must_change_password']


class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class TwoFactorCodeSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6)