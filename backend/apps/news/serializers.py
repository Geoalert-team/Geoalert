from django.core.validators import FileExtensionValidator
from rest_framework import serializers

from apps.news.models import Announcement
from apps.reports.serializers import validate_photo_size

PHOTO_TYPES = ['jpg', 'jpeg', 'png', 'webp']


class AnnouncementWriteSerializer(serializers.ModelSerializer):
    """
    Posting or editing an announcement: title, text and an optional photo
    (a real image, checked by Pillow as report photos are). remove_photo
    drops the photo; a replaced or removed photo's file is deleted too.
    """
    body = serializers.CharField(max_length=5000)
    photo = serializers.ImageField(
        required=False,
        validators=[validate_photo_size, FileExtensionValidator(PHOTO_TYPES, 'Use a JPEG, PNG or WebP photo.')],
    )
    remove_photo = serializers.BooleanField(required=False, default=False, write_only=True)

    class Meta:
        model = Announcement
        fields = ['title', 'body', 'photo', 'remove_photo']

    def create(self, validated_data):
        validated_data.pop('remove_photo', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        remove = validated_data.pop('remove_photo', False)
        old = instance.photo.name if instance.photo else ''
        if remove and 'photo' not in validated_data:
            instance.photo = None
        instance = super().update(instance, validated_data)
        if old and old != (instance.photo.name if instance.photo else ''):
            instance.photo.storage.delete(old)
        return instance
