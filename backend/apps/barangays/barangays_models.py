from django.contrib.gis.db import models


class Barangay(models.Model):
    name         = models.CharField(max_length=100, unique=True)
    municipality = models.CharField(max_length=100, default='Talisay City')
    boundary     = models.MultiPolygonField(srid=4326, null=True, blank=True)

    class Meta:
        db_table = 'barangay'

    def __str__(self):
        return self.name