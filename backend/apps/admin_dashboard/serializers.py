from rest_framework import serializers
from apps.accounts.models import User, Role
from apps.admin_dashboard.models import AuditLog


class RolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'description']



class UserListSerializer(serializers.ModelSerializer):
    role = RolesSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'role', 'is_active', 'last_login', 'created_at']



class UserCreateSerializer(serializers.ModelSerializer):
    role_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email',  'role_id', ]

    def create(self, validated_data):
        role_id = validated_data.pop('role_id')
        role = Role.objects.get(id=role_id)

        import secrets
        import string
        temp_password = ''.join(
            secrets.choice(string.ascii_letters + string.digits + '!@#')
            for _ in range(12)
        )

        user = User.objects.create_user(
            email=validated_data['email'],
            password=temp_password,
            full_name=validated_data['full_name'],
        )
        user.role = role
        user.save()

        # Attach temp password to instance for the view to return
        user._temp_password = temp_password
        return user



class UserUpdateSerializer(serializers.ModelSerializer):
    role_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'role_id', 'is_active']

    def update(self, instance, validated_data):
        role_id = validated_data.pop('role_id', None)
        if role_id:
            instance.role = Role.objects.get(id=role_id)

        instance.full_name = validated_data.get('full_name', instance.full_name)
        instance.email     = validated_data.get('email', instance.email)
        instance.is_active = validated_data.get('is_active', instance.is_active)
        instance.save()
        return instance

class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_email', 'user_name', 'action', 'target_table', 'target_id', 'details', 'ip_address', 'created_at']

        