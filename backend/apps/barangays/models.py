from django.contrib.gis.db import models


class Barangay(models.Model):
    id           = models.BigAutoField(primary_key=True, db_column='brgy_id')
    name         = models.CharField(max_length=100, unique=True, db_column='brgy_name')
    municipality = models.CharField(max_length=100, default='Talisay City', db_column='brgy_municipality')
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
