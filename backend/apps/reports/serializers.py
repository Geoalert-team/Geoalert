from rest_framework import serializers
from apps.reports.models import IncidentReport
from apps.hazards.serializers import HazardTypeSerializer
from apps.barangays.serializers import BarangaySerializer

# A phone photo is 2-4 MB. Past this it is someone uploading something that
# is not a snapshot, and the barangay's connection has to carry it.
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def validate_photo_size(photo):
    if photo and photo.size > MAX_PHOTO_BYTES:
        mb = MAX_PHOTO_BYTES // (1024 * 1024)
        raise serializers.ValidationError(
            f'That photo is {photo.size / 1024 / 1024:.1f} MB. '
            f'Please use one under {mb} MB.'
        )
    return photo


class IncidentReportSerializer(serializers.ModelSerializer):
    hazard_type_details = HazardTypeSerializer(source='hazard_type', read_only=True)
    barangay_details = BarangaySerializer(source='barangay', read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)

    class Meta:
        model = IncidentReport
        fields = [
            'id',
            'submitted_by',
            'submitted_by_name',
            'barangay',
            'barangay_details',
            'hazard_type',
            'hazard_type_details',
            'description',
            'casualties_dead',
            'casualties_injured',
            'casualties_missing',
            'displaced',
            'reporter_name',
            'agency',
            'position',
            'severity_estimate',
            'photo',
            'status',
            'review_note',
            'reviewed_by',
            'reviewed_by_name',
            'created_at',
            'reviewed_at',
            'validated_at',
        ]

    def to_representation(self, instance):
        """
        Make the photo URL absolute.

        DRF builds an absolute URL only when the serializer has the request
        in its context; without it the field comes back as '/media/...',
        which the React app on :3000 would resolve against itself rather
        than the API on :8000 and render as a broken image. The views pass
        the request, and this is the belt to that braces: if one ever
        forgets, the URL is still built from the API's own host.
        """
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request is not None and instance.photo:
            data['photo'] = request.build_absolute_uri(instance.photo.url)
        return data

class IncidentReportCreateSerializer(serializers.ModelSerializer):
    # No casualty or displaced counts: while a hazard is active only the
    # DRRMO records how many people are affected.

    # Declared rather than inherited so the size check is attached. Being a
    # serializers.ImageField, Pillow opens and verifies the upload, so a file
    # renamed to .jpg is rejected on its contents rather than its extension.
    photo = serializers.ImageField(
        required=False, allow_null=True, validators=[validate_photo_size],
    )

    class Meta:
        model = IncidentReport
        fields = [
            'barangay',
            'hazard_type',
            'description',
            'agency',
            'position',
            'severity_estimate',
            'photo',
        ]

class IncidentReportReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = IncidentReport
        fields = ['status', 'review_note']
