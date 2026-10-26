"""
Shared setup for the database-backed fire tests: two barangays side by side,
a purok in each, Fire and Flood types, two DRRMO officers and barangay
personnel in each barangay. Coordinates are meters from (LNG, LAT).
"""
import math
from datetime import timedelta

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType, HazardZone
from apps.history.models import HistoricalRecord
from apps.reports.decide import fire_geometry
from apps.reports.models import IncidentReport

LAT, LNG = 10.74, 122.97
M = 1 / 111_320


def box(x0, y0, x1, y1):
    """A rectangle given in meters from (LNG, LAT)."""
    sx = M / math.cos(math.radians(LAT))
    pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Polygon([(LNG + x * sx, LAT + y * M) for x, y in pts], srid=4326)


class FireSetupMixin:
    def setUp(self):
        officer, personnel = (Role.objects.create(name=n) for n in ('DRRMO_Officer', 'Barangay_Personnel'))
        self.home = Barangay.objects.create(name='Home', municipality='Talisay',
                                            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        self.next = Barangay.objects.create(name='Next door', municipality='Talisay',
                                            boundary=MultiPolygon(box(500, -500, 1500, 500), srid=4326))
        self.near = Purok.objects.create(barangay=self.home, name='Purok Near', kind='purok', source='estimated',
                                         boundary=MultiPolygon(box(-100, -100, 100, 100), srid=4326))
        self.far = Purok.objects.create(barangay=self.next, name='Purok Far', kind='purok', source='estimated',
                                        boundary=MultiPolygon(box(700, -100, 900, 100), srid=4326))
        self.fire = HazardType.objects.create(name='Fire', logo_class='fire', is_active=True)
        self.flood = HazardType.objects.create(name='Flood', logo_class='flood', is_active=True)

        def user(name, role, barangay=None):
            return User.objects.create_user(email=f'{name}@test.ph', password='x', full_name=name.title(),
                                            role=role, assigned_barangay=barangay)
        self.officer = user('officer', officer)
        self.second = user('second', officer)
        self.reporter = user('reporter', personnel, self.home)
        self.neighbour = user('neighbour', personnel, self.next)

    def report(self, *puroks, hazard=None, **kw):
        r = IncidentReport.objects.create(submitted_by=self.reporter, barangay=self.home,
                                          hazard_type=hazard or self.fire, description='Smoke from a house',
                                          started_at=timezone.now() - timedelta(minutes=20), **kw)
        r.puroks.set(puroks)
        return r

    def history(self, purok, n):
        for i in range(n):
            rec = HistoricalRecord.objects.create(barangay=purok.barangay, hazard_type=self.fire, severity_level='Green',
                                                  occurred_at=timezone.now() - timedelta(days=30 * (i + 1)))
            rec.puroks.add(purok)

    def zone(self, purok, **kw):
        fields = {'hazard_type': self.fire, 'barangay': purok.barangay, 'severity': 'Orange', 'status': 'Active',
                  'published_by': self.officer, 'geometry': fire_geometry([purok.boundary.point_on_surface])}
        fields.update(kw)
        return HazardZone.objects.create(**fields)
