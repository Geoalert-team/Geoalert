import os

from rest_framework import serializers

from apps.reports.serializers import photo_url
from apps.tutorials.models import TutorialVideo, VideoCategory
from apps.tutorials.youtube import parse_youtube_id

# The most the Supabase free plan takes in one file. Longer videos go on YouTube.
MAX_VIDEO_BYTES = 50 * 1024 * 1024

NOT_MP4 = "That file isn't an MP4 video."
BAD_LINK = "That isn't a YouTube video link."
NEED_LINK = 'Paste the YouTube link for this video.'
NEED_FILE = 'Choose the MP4 file for this video.'
MIXED = 'Send either a YouTube link or an MP4 file, not both.'


def name_taken(name):
    return f'There is already a category called {name}.'


def validate_mp4(file):
    """
    An uploaded video must be an MP4 of at most 50 MB, and really an MP4: an
    MP4 file starts with a box whose type, in bytes 4 to 7, is "ftyp", so a
    renamed text or image file is refused. The content type is set here,
    whatever the browser sent, so storage serves the file as a video.
    """
    if os.path.splitext(file.name or '')[1].lower() != '.mp4':
        raise serializers.ValidationError(NOT_MP4)
    if file.size > MAX_VIDEO_BYTES:
        raise serializers.ValidationError(
            f'That video is {file.size / 1024 / 1024:.1f} MB. Please use one under 50 MB, or put it on YouTube.'
        )
    file.seek(0)
    head = file.read(12)
    file.seek(0)
    if len(head) < 8 or head[4:8] != b'ftyp':
        raise serializers.ValidationError(NOT_MP4)
    file.content_type = 'video/mp4'
    return file


class VideoCategorySerializer(serializers.ModelSerializer):
    """
    A category, with how many videos it holds (read from the queryset's
    annotation). A name another category already has, ignoring case, is
    refused with that category's own spelling.
    """
    name = serializers.CharField(max_length=60)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    video_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = VideoCategory
        fields = ['id', 'name', 'description', 'video_count']

    def validate_name(self, value):
        others = VideoCategory.objects.filter(name__iexact=value)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        existing = others.first()
        if existing is not None:
            raise serializers.ValidationError(name_taken(existing.name))
        return value


class TutorialVideoSerializer(serializers.ModelSerializer):
    """A video as the What To Do page reads it."""
    category = serializers.SerializerMethodField()
    youtube_id = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TutorialVideo
        fields = ['id', 'title', 'description', 'category', 'source_type',
                  'youtube_id', 'file_url', 'file_size', 'created_at']

    def get_category(self, obj):
        return {'id': str(obj.category_id), 'name': obj.category.name}

    def get_youtube_id(self, obj):
        return obj.youtube_id or None

    def get_file_url(self, obj):
        # Absolute: signed and short-lived on Supabase, as report photos are
        return photo_url(obj.file, self.context.get('request'))


class TutorialVideoWriteSerializer(serializers.ModelSerializer):
    """
    Adding or editing one video. A YouTube video is sent as the pasted link
    (only its ID is kept); an MP4 as the file. An edit can switch a video
    between the two, with the new media in the same request; the old file is
    then deleted, as it is when a file is replaced.
    """
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    youtube_url = serializers.CharField(required=False, write_only=True)
    file = serializers.FileField(required=False, validators=[validate_mp4])

    class Meta:
        model = TutorialVideo
        fields = ['category', 'title', 'description', 'source_type', 'youtube_url', 'file']

    def validate(self, attrs):
        instance = self.instance
        kind = attrs.get('source_type') or instance.source_type
        switching = instance is None or kind != instance.source_type
        url = attrs.pop('youtube_url', None)
        file = attrs.get('file')

        if kind == 'youtube':
            if file is not None:
                raise serializers.ValidationError({'source_type': MIXED})
            if url is None:
                if switching:
                    raise serializers.ValidationError({'youtube_url': NEED_LINK})
            else:
                youtube_id = parse_youtube_id(url)
                if not youtube_id:
                    raise serializers.ValidationError({'youtube_url': BAD_LINK})
                attrs['youtube_id'] = youtube_id
        else:
            if url is not None:
                raise serializers.ValidationError({'source_type': MIXED})
            if file is None and switching:
                raise serializers.ValidationError({'file': NEED_FILE})
        attrs['source_type'] = kind
        return attrs

    @staticmethod
    def _media(data):
        """The fields that keep a row one kind: no file for YouTube, no ID for an upload."""
        if data['source_type'] == 'youtube':
            data['file'] = ''
            data['file_size'] = None
        else:
            if 'file' in data:
                data['file_size'] = data['file'].size
            data['youtube_id'] = ''
        return data

    def create(self, validated_data):
        return super().create(self._media(validated_data))

    def update(self, instance, validated_data):
        old = instance.file.name if instance.file else ''
        instance = super().update(instance, self._media(validated_data))
        if old and old != (instance.file.name if instance.file else ''):
            instance.file.storage.delete(old)
        return instance
