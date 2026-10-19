"""
Taking back a field mark dropped by mistake.

A stray mark is not cosmetic: one that disagrees with the outline notifies
the officer who published the zone and nudges them to reshape a live
hazard. The rules that matter are who may remove one -- a mark is evidence
several people contribute to -- and that the counts settle afterwards.
"""
import math

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType, HazardZone, ZoneFieldMark
from apps.notifications.models import Notification

LAT, LNG = 10.74, 122.97
M = 1 / 111_320


def at(x, y):
    """A point x metres east and y metres north of (LNG, LAT)."""
    return Point(LNG + x * (M / math.cos(math.radians(LAT))), LAT + y * M, srid=4326)


def box(x0, y0, x1, y1):
    sx = M / math.cos(math.radians(LAT))
    pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Polygon([(LNG + x * sx, LAT + y * M) for x, y in pts], srid=4326)


class FieldMarkRemovalTests(TestCase):
    def setUp(self):
        self.bp_role, _ = Role.objects.get_or_create(name='Barangay_Personnel')
        self.drrmo_role, _ = Role.objects.get_or_create(name='DRRMO_Officer')

        self.barangay = Barangay.objects.create(
            name='Poblacion', municipality='Talisay',
            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326),
        )
        self.hazard = HazardType.objects.create(name='Flood', logo_class='flood', is_active=True)

        self.officer = User.objects.create_user(
            email='officer@talisay.gov.ph', password='x', full_name='Officer One',
            role=self.drrmo_role,
        )
        self.marker = User.objects.create_user(
            email='bp1@talisay.gov.ph', password='x', full_name='Marker One',
            role=self.bp_role, assigned_barangay=self.barangay,
        )
        self.other = User.objects.create_user(
            email='bp2@talisay.gov.ph', password='x', full_name='Someone Else',
            role=self.bp_role, assigned_barangay=self.barangay,
        )

        # The zone runs 0..100 m east. A mark at 200 m is outside it.
        self.zone = HazardZone.objects.create(
            hazard_type=self.hazard, barangay=self.barangay,
            severity='Orange', status='Active', published_by=self.officer,
            geometry=MultiPolygon(box(0, 0, 100, 100), srid=4326),
            outline=box(0, 0, 100, 100), description='flood',
        )

    def mark(self, user, kind='Affected', point=None):
        return ZoneFieldMark.objects.create(
            zone=self.zone, kind=kind,
            location=point if point is not None else at(50, 50),
            created_by=user,
        )

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def url(self, mark):
        return f'/api/hazards/{self.zone.id}/marks/{mark.id}/'

    # ---------------------------------------------------------- who may

    def test_you_can_take_back_your_own_mark(self):
        mark = self.mark(self.marker)
        res = self.client_for(self.marker).delete(self.url(mark))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    def test_you_cannot_remove_someone_elses(self):
        mark = self.mark(self.marker)
        res = self.client_for(self.other).delete(self.url(mark))
        self.assertEqual(res.status_code, 403)
        self.assertTrue(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    def test_the_publishing_officer_may_remove_any_mark(self):
        mark = self.mark(self.marker)
        res = self.client_for(self.officer).delete(self.url(mark))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    def test_an_officer_who_published_a_different_zone_may_not(self):
        stranger = User.objects.create_user(
            email='officer2@talisay.gov.ph', password='x', full_name='Officer Two',
            role=self.drrmo_role,
        )
        mark = self.mark(self.marker)
        res = self.client_for(stranger).delete(self.url(mark))
        self.assertEqual(res.status_code, 403)
        self.assertTrue(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    def test_signing_in_is_required(self):
        mark = self.mark(self.marker)
        self.assertIn(APIClient().delete(self.url(mark)).status_code, (401, 403))
        self.assertTrue(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    # ------------------------------------------------------ when it may

    def test_a_mark_on_a_resolved_zone_is_part_of_the_record(self):
        mark = self.mark(self.marker)
        self.zone.status = 'Resolved'
        self.zone.save(update_fields=['status'])
        res = self.client_for(self.marker).delete(self.url(mark))
        self.assertEqual(res.status_code, 400)
        self.assertTrue(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    def test_a_mark_on_a_withdrawn_zone_stays_too(self):
        mark = self.mark(self.marker)
        self.zone.status = 'Retracted'
        self.zone.save(update_fields=['status'])
        self.assertEqual(self.client_for(self.marker).delete(self.url(mark)).status_code, 400)

    # ------------------------------------------------------ wrong paths

    def test_a_mark_belonging_to_another_zone_is_not_found_here(self):
        elsewhere = HazardZone.objects.create(
            hazard_type=self.hazard, barangay=self.barangay,
            severity='Green', status='Active', published_by=self.officer,
            geometry=MultiPolygon(box(300, 300, 400, 400), srid=4326),
            outline=box(300, 300, 400, 400), description='other',
        )
        mark = ZoneFieldMark.objects.create(
            zone=elsewhere, kind='Clear', location=at(350, 350), created_by=self.marker,
        )
        res = self.client_for(self.marker).delete(f'/api/hazards/{self.zone.id}/marks/{mark.id}/')
        self.assertEqual(res.status_code, 404)
        self.assertTrue(ZoneFieldMark.objects.filter(pk=mark.pk).exists())

    def test_removing_the_same_mark_twice_is_not_found(self):
        mark = self.mark(self.marker)
        client = self.client_for(self.marker)
        self.assertEqual(client.delete(self.url(mark)).status_code, 200)
        self.assertEqual(client.delete(self.url(mark)).status_code, 404)

    # ----------------------------------------------- the counts settle

    def test_the_counts_come_back_without_the_removed_mark(self):
        # Affected inside the outline agrees with it; Affected outside does not.
        self.mark(self.marker, 'Affected', at(50, 50))
        self.mark(self.other, 'Affected', at(60, 60))
        wrong = self.mark(self.marker, 'Affected', at(200, 50))  # outside: disagrees

        before = self.client_for(self.marker).get(f'/api/hazards/{self.zone.id}/marks/').data
        self.assertEqual(len(before['results']), 3)
        self.assertEqual(before['disagreeing'], 1)

        res = self.client_for(self.marker).delete(self.url(wrong))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['removed'], str(wrong.id))
        self.assertEqual(len(res.data['results']), 2)
        self.assertEqual(res.data['disagreeing'], 0)

    def test_other_peoples_marks_are_left_alone(self):
        mine = self.mark(self.marker)
        theirs = self.mark(self.other)
        self.client_for(self.marker).delete(self.url(mine))
        self.assertTrue(ZoneFieldMark.objects.filter(pk=theirs.pk).exists())

    # ------------------------------------------------- telling the officer

    def test_the_officer_hears_that_a_disagreement_was_taken_back(self):
        wrong = self.mark(self.marker, 'Affected', at(200, 50))
        Notification.objects.all().delete()
        self.client_for(self.marker).delete(self.url(wrong))
        notes = Notification.objects.filter(recipient=self.officer)
        self.assertEqual(notes.count(), 1)
        self.assertIn('taken back', notes.first().content)

    def test_removing_an_agreeing_mark_does_not_bother_the_officer(self):
        fine = self.mark(self.marker, 'Clear', at(200, 50))  # clear, outside: agrees
        Notification.objects.all().delete()
        self.client_for(self.marker).delete(self.url(fine))
        self.assertEqual(Notification.objects.filter(recipient=self.officer).count(), 0)

    def test_the_officer_does_not_notify_themselves(self):
        wrong = ZoneFieldMark.objects.create(
            zone=self.zone, kind='Affected', location=at(200, 50), created_by=self.officer,
        )
        Notification.objects.all().delete()
        self.client_for(self.officer).delete(self.url(wrong))
        self.assertEqual(Notification.objects.filter(recipient=self.officer).count(), 0)

    # --------------------------------------------- what the client is told

    def test_your_own_mark_comes_back_removable(self):
        self.mark(self.marker)
        res = self.client_for(self.marker).get(f'/api/hazards/{self.zone.id}/marks/')
        self.assertTrue(res.data['results'][0]['can_remove'])

    def test_someone_elses_does_not(self):
        self.mark(self.other)
        res = self.client_for(self.marker).get(f'/api/hazards/{self.zone.id}/marks/')
        self.assertFalse(res.data['results'][0]['can_remove'])

    def test_the_publishing_officer_sees_every_mark_as_removable(self):
        self.mark(self.marker)
        self.mark(self.other)
        res = self.client_for(self.officer).get(f'/api/hazards/{self.zone.id}/marks/')
        self.assertTrue(all(r['can_remove'] for r in res.data['results']))

    def test_nothing_is_removable_once_the_zone_is_resolved(self):
        self.mark(self.marker)
        self.zone.status = 'Resolved'
        self.zone.save(update_fields=['status'])
        res = self.client_for(self.officer).get(f'/api/hazards/{self.zone.id}/marks/')
        self.assertFalse(res.data['results'][0]['can_remove'])

    def test_what_the_flag_says_matches_what_delete_does(self):
        mine = self.mark(self.marker)
        theirs = self.mark(self.other)
        client = self.client_for(self.marker)
        rows = {r['id']: r['can_remove'] for r in
                client.get(f'/api/hazards/{self.zone.id}/marks/').data['results']}
        self.assertEqual(client.delete(self.url(mine)).status_code,
                         200 if rows[str(mine.id)] else 403)
        self.assertEqual(client.delete(self.url(theirs)).status_code,
                         200 if rows[str(theirs.id)] else 403)
