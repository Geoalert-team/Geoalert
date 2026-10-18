from rest_framework import serializers
from apps.reports.models import IncidentReport, ReportPhoto
from apps.hazards.serializers import HazardTypeSerializer
from apps.barangays.serializers import BarangaySerializer

# A phone photo is 2-4 MB. Past this it is someone uploading something that
# is not a snapshot, and the barangay's connection has to carry it.
MAX_PHOTO_BYTES = 5 * 1024 * 1024

# Enough for a wide shot, a close one and a couple of angles. The cap is
# here so one report cannot fill the bucket or hold a request open for
# minutes on a barangay's connection.
MAX_PHOTOS_PER_REPORT = 5


def validate_photo_size(photo):
    if photo and photo.size > MAX_PHOTO_BYTES:
        mb = MAX_PHOTO_BYTES // (1024 * 1024)
        raise serializers.ValidationError(
            f'That photo is {photo.size / 1024 / 1024:.1f} MB. '
            f'Please use one under {mb} MB.'
        )
    return photo


def photo_url(image, request=None):
    """
    The URL the browser should fetch for a stored image.

    Two storage backends give two different URLs. Local disk gives
    '/media/incident_reports/...', relative, which the React app on :3000
    would resolve against itself rather than the API on :8000 and render as
    a broken image, so it needs the API's host prepending. Supabase Storage
    gives a full signed URL, already absolute and carrying an AWS Signature
    Version 4 query string; prepending anything to that would corrupt it.

    So the host is added only when the URL is relative. Testing the shape of
    the URL rather than which backend is configured keeps this correct if
    the backend changes under it.
    """
    if not image:
        return None
    url = image.url
    if request is not None and not url.startswith(('http://', 'https://')):
        url = request.build_absolute_uri(url)
    return url


class ReportPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ReportPhoto
        fields = ['id', 'url', 'uploaded_at']

    def get_url(self, obj):
        return photo_url(obj.image, self.context.get('request'))


class IncidentReportSerializer(serializers.ModelSerializer):
    hazard_type_details = HazardTypeSerializer(source='hazard_type', read_only=True)
    barangay_details = BarangaySerializer(source='barangay', read_only=True)
    hazard_zone = serializers.PrimaryKeyRelatedField(read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)
    photos = ReportPhotoSerializer(many=True, read_only=True)
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    def get_latitude(self, obj):
        return round(obj.location.y, 6) if obj.location else None

    def get_longitude(self, obj):
        return round(obj.location.x, 6) if obj.location else None

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
            'photos',
            'status',
            'review_note',
            'reviewed_by',
            'reviewed_by_name',
            'created_at',
            'reviewed_at',
            'validated_at',
            # The zone published from this report, if any
            'hazard_zone',
            # Where the reporter saw it, or null when no pin was dropped
            'latitude', 'longitude',
        ]


class IncidentReportCreateSerializer(serializers.ModelSerializer):
    # No casualty or displaced counts: while a hazard is active only the
    # DRRMO records how many people are affected.

    # A list, because a report usually carries more than one picture. Each
    # entry is a serializers.ImageField, so Pillow opens and verifies it and
    # a file renamed to .jpg is refused on its contents rather than its
    # extension. ListField validates every item before anything is saved,
    # which is what keeps one bad file in a batch of four from leaving the
    # other three uploaded against a report that was never created.
    photos = serializers.ListField(
        child=serializers.ImageField(validators=[validate_photo_size]),
        required=False, allow_empty=True, max_length=MAX_PHOTOS_PER_REPORT,
        error_messages={
            'max_length': f'Please attach at most {MAX_PHOTOS_PER_REPORT} photos.',
        },
    )

    # Optional map pin. Two plain numbers rather than GeoJSON, because a
    # report with photos arrives as multipart form data.
    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)

    class Meta:
        model = IncidentReport
        fields = [
            'barangay',
            'hazard_type',
            'description',
            'agency',
            'position',
            'severity_estimate',
            'photos',
            'latitude',
            'longitude',
        ]

    def validate(self, attrs):
        from django.contrib.gis.geos import Point
        from apps.hazards.geometry import city_outline

        lat = attrs.pop('latitude', None)
        lng = attrs.pop('longitude', None)
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({'location': 'Send both latitude and longitude, or neither.'})
        if lat is not None:
            point = Point(lng, lat, srid=4326)
            city = city_outline()
            if city is not None and not city.buffer(0.002).contains(point):
                raise serializers.ValidationError(
                    {'location': 'The pin is outside Talisay City. Place it where you saw the hazard.'}
                )
            attrs['location'] = point
        return attrs

    def create(self, validated_data):
        """
        Save the report and its photos together, or save neither.

        The files are popped before the model is created, because `photos`
        is not a field on IncidentReport -- it is rows in another table. The
        view wraps this in a transaction, so a photo that fails to upload
        takes the whole report back with it rather than leaving a report
        whose pictures are missing without saying so.
        """
        photos = validated_data.pop('photos', [])
        report = super().create(validated_data)
        for image in photos:
            ReportPhoto.objects.create(report=report, image=image)
        return report


class IncidentReportReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = IncidentReport
        fields = ['status', 'review_note']
