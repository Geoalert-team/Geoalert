"""
The 10 first aid videos the What To Do page hardcoded (frontend
safetyGuides.js, VIDEOS) move into the database, under "First Aid", in the
order they were listed. Created one by one so created_at keeps that order.
"""
from django.db import migrations

SEED = [
    ('gn6xt1ca8A0', 'How to use your first aid kit'),
    ('ea1RJUOiNfQ', 'How to do the primary survey'),
    ('GmqXqwSV3bo', 'The recovery position'),
    ('NxO5LvgqZe0', 'How to treat severe bleeding'),
    ('2v8vlXgGXwE', 'How to treat a fracture'),
    ('fKzdiuseEIw', 'How to bandage a hand'),
    ('PwfBGkBXkFA', 'How to make a sling'),
    ('4e7evinsfm0', 'How to treat cuts and grazes'),
    ('Uqy2IUhYkVA', 'What to do if someone has a spinal cord injury'),
    ('0jps5SZlTdo', 'How to bandage a sprain'),
]
CATEGORY = 'First Aid'


def seed_first_aid(apps, schema_editor):
    VideoCategory = apps.get_model('tutorials', 'VideoCategory')
    TutorialVideo = apps.get_model('tutorials', 'TutorialVideo')
    category = VideoCategory.objects.create(name=CATEGORY)
    for youtube_id, title in SEED:
        TutorialVideo.objects.create(category=category, title=title, source_type='youtube', youtube_id=youtube_id)


def remove_first_aid(apps, schema_editor):
    VideoCategory = apps.get_model('tutorials', 'VideoCategory')
    TutorialVideo = apps.get_model('tutorials', 'TutorialVideo')
    category = VideoCategory.objects.filter(name=CATEGORY).first()
    if category is None:
        return
    TutorialVideo.objects.filter(category=category, youtube_id__in=[i for i, _ in SEED]).delete()
    if not TutorialVideo.objects.filter(category=category).exists():
        category.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tutorials', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_first_aid, remove_first_aid),
    ]
