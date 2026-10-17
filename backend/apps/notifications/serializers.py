from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    # The bell needs more than an opaque alert UUID: without the zone id it
    # can't take the user to the hazard, and without type/severity it can't
    # colour the row. Read-only and flattened so the frontend doesn't have
    # to make a second request per notification.
    hazard   = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    link     = serializers.SerializerMethodField()

    class Meta:
        model  = Notification
        fields = ['id', 'hazard_alert', 'hazard', 'category', 'link',
                  'content', 'is_read', 'sent_at', 'read_at']

    def get_hazard(self, obj):
        alert = obj.hazard_alert
        if alert is None:
            return None

        zone = alert.hazard_zone
        return {
            'alert_id': str(alert.id),
            'zone_id':  str(zone.id) if zone else None,
            'type':     alert.hazard_type.name if alert.hazard_type else None,
            'severity': alert.severity,
            'barangay': zone.barangay.name if zone and zone.barangay else None,
            # Lets the bell grey out alerts whose hazard has since been resolved
            'status':   zone.status if zone else None,
        }

    def get_category(self, obj):
        """
        Which group the bell files this notification under: it picks the icon,
        the title and the tab. Anything created against a hazard alert is a
        hazard; the rest is inferred from the wording until those
        notifications are created with a category of their own.
        """
        if obj.hazard_alert_id or obj.hazard_zone_id:
            return 'hazard'

        content = (obj.content or '').lower()
        # A withdrawal notice carries no hazard_alert on purpose (it would
        # inflate that alert's reach figures), but it is still about a hazard
        # and belongs with the hazard alerts in the bell.
        if 'withdrawn' in content:
            return 'hazard'
        if 'report' in content:
            return 'report'
        if any(word in content for word in ('password', 'two-factor', 'sign in', 'login', 'locked')):
            return 'security'
        return 'account'

    def get_link(self, obj):
        """
        Where tapping the notification should go, or None to leave it inert.
        """
        alert = obj.hazard_alert
        if alert and alert.hazard_zone_id:
            return f'/map?zone={alert.hazard_zone_id}'
        zone = obj.hazard_zone
        if zone is not None:
            # Waiting for approval or withdrawn: not on the public map, so
            # the dashboard is where it can be acted on or read about.
            if zone.status == 'Active':
                return f'/map?zone={zone.id}'
            return '/app/dashboard'
        return None