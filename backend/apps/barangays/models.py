from django.contrib.gis.db import models
from django.db import connection


class Barangay(models.Model):
    id           = models.BigAutoField(primary_key=True, db_column='brgy_id')
    name         = models.CharField(max_length=100, unique=True, db_column='brgy_name')
    municipality = models.CharField(max_length=100, default='Talisay City', db_column='brgy_municipality')
    # With municipality, where the BFP fire log files a fire (its columns
    # C-E: region, province / district, city / municipality). Every report
    # reads them from its barangay rather than storing its own copy.
    province     = models.CharField(max_length=100, default='Cebu', db_column='brgy_province')
    region       = models.CharField(max_length=100, default='Region VII (Central Visayas)', db_column='brgy_region')
    boundary     = models.MultiPolygonField(srid=4326, null=True, blank=True, db_column='brgy_boundary')

    class Meta:
        db_table = 'barangay'

    def __str__(self):
        return self.name


class Purok(models.Model):
    """
    A purok, sitio, zone or named subdivision inside a barangay.

    Until the Barangay Hall sends official lines, the boundaries are estimates
    (manage.py build_purok_estimates); load_puroks swaps official ones in.
    """
    KINDS = ['purok', 'sitio', 'zone', 'subdivision']
    SOURCES = ['estimated', 'community', 'official']

    id         = models.BigAutoField(primary_key=True, db_column='prk_id')
    barangay   = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='puroks', db_column='brgy_id')
    name       = models.CharField(max_length=100, db_column='prk_name')
    kind       = models.CharField(max_length=12, choices=[(k, k) for k in KINDS], db_column='prk_kind')
    # The sitio a purok sits in ("Purok Sambag, Laray"), for its label
    parent     = models.CharField(max_length=100, blank=True, default='', db_column='prk_parent')
    boundary   = models.MultiPolygonField(srid=4326, db_column='prk_boundary')
    # estimated: grown from a researched point; community: an outline drawn
    # on Wikimapia or OpenStreetMap; official: from the Barangay Hall
    source     = models.CharField(max_length=10, choices=[(s, s) for s in SOURCES], db_column='prk_source')
    # How sure the researched point is (high / medium / low); blank for official
    confidence = models.CharField(max_length=6, blank=True, default='', db_column='prk_confidence')

    class Meta:
        db_table = 'purok'
        constraints = [models.UniqueConstraint(fields=['barangay', 'name'], name='purok_unique_name_per_barangay')]

    def __str__(self):
        return f'{self.name}, {self.barangay}'

    @classmethod
    def outlines_version(cls):
        """
        A fingerprint that changes when a purok or its barangay is added,
        edited or removed. load_puroks writes in bulk and often from another
        laptop, so no signal or local cache would see it; Postgres gives every
        new version of a row a new xmin, and reading those reads no outlines.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT md5(string_agg(p.prk_id::text || ':' || p.xmin::text || ':' || b.xmin::text, "
                "',' ORDER BY p.prk_id)) FROM purok p JOIN barangay b ON b.brgy_id = p.brgy_id"
            )
            return cursor.fetchone()[0] or 'empty'

    @classmethod
    def member_counts(cls):
        """
        {(barangay id, name): how many puroks name it as parent}. A purok in it
        is a sitio drawn around its puroks, so its outline overlaps theirs.
        """
        from django.db.models import Count
        rows = (cls.objects.exclude(parent='').values('barangay_id', 'parent')
                .annotate(n=Count('id')).order_by())
        names = set(cls.objects.values_list('barangay_id', 'name'))
        return {(r['barangay_id'], r['parent']): r['n'] for r in rows if (r['barangay_id'], r['parent']) in names}
