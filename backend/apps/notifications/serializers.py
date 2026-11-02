from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    # The bell needs more than an opaque alert UUID: without the zone id it
    # can't take the user to the hazard, and without type/severity it can't
    # colour the row. Read-only and flattened so the frontend doesn't have
    # to make a second request per notification.
    hazard   = serializers.SerializerMethodField()
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
        # A report notice: the reports are on the dashboard (BFP's fire reports)
        if obj.category == Notification.REPORT:
            return '/app/dashboard'
        return None