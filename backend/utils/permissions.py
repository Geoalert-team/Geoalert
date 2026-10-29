from rest_framework.permissions import BasePermission


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'role') and
            request.user.role is not None and
            request.user.role.name == 'System_Admin'
        )


class IsDRRMOOfficer(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request.user, 'role') or request.user.role is None:
            return False
        return request.user.role.name in ['DRRMO_Officer', 'System_Admin']


class IsBarangayPersonnel(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request.user, 'role') or request.user.role is None:
            return False
        return request.user.role.name in [
            'Barangay_Personnel', 'DRRMO_Officer', 'System_Admin'
        ]


# Bureau of Fire Protection personnel answer fires and nothing else: they see
# them, close them with the BFP figures and export the fire history. Every
# view a BFP account can reach keeps them to fires itself.
BFP_ROLE = 'BFP_Personnel'


def is_bfp(user):
    role = getattr(user, 'role', None)
    return role is not None and role.name == BFP_ROLE


class IsBFPPersonnel(BasePermission):
    """The fire work: BFP personnel, and DRRMO and admins, who can do it too."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request.user, 'role') or request.user.role is None:
            return False
        return request.user.role.name in [
            BFP_ROLE, 'DRRMO_Officer', 'System_Admin'
        ]