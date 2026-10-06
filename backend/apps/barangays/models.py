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
