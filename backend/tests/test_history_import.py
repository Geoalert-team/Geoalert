"""
POST /api/history/import/: DRRMO brings the BFP fire log or the flood and
landslide log in from the History page. Checking saves nothing; importing
adds only rows not already in the history, and is logged. Against a real
database, with workbooks built here in the logs' layouts.
"""
import io
from datetime import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.hazards.models import HazardType
from apps.history.import_views import HistoryImportView
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def workbook_bytes(sheets):
    """{sheet name: [rows]} as .xlsx bytes, the sheets in the order given."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


HEADERS = [['header'], ['header'], ['header']]


def fire_row(city='TALISAY CITY', location='12 RIZAL ST, BRGY HOME', day=datetime(2024, 3, 5)):
    """One row of the BFP log, columns A to W."""
    row = [None] * 23
    row[0], row[1], row[4], row[5] = day, '2230H', city, location
    row[6], row[7] = 'RESIDENTIAL', 'SINGLE AND TWO FAMILY DWELLING'
    row[20], row[22] = 5000, '1ST ALARM'
    return row


FIRE_LOG = workbook_bytes({'Sheet1': HEADERS + [fire_row(), fire_row(city='BACOLOD CITY')]})

FLOOD_ROW = [datetime(2021, 6, 12), 1855, 'VI', 'NEGROS OCCIDENTAL', 'Talisay City', 'Riverside', 'FLOOD',
             'RIVER OVERFLOW', 'Heavy rain', None, None, 12, 40, 'Water knee-deep in the riverside homes.']
FLOOD_LOG = workbook_bytes({
    'Flood': HEADERS + [FLOOD_ROW],
    'Landslide': HEADERS,
    'By Barangay': [['header'], [datetime(2021, 6, 12), 'FLOOD', 'VI', 'NEGROS OCCIDENTAL', 'Talisay City',
                                 'Home', None, None, 12]],
})


class HistoryImportViewTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        HazardType.objects.create(name='Landslide', logo_class='landslide', is_active=True)

    def post(self, content, name='log.xlsx', user=None, **data):
        upload = SimpleUploadedFile(name, content, content_type=XLSX)
        request = APIRequestFactory().post('/api/history/import/', {'file': upload, **data}, format='multipart')
        force_authenticate(request, user=user or self.officer)
        return HistoryImportView.as_view()(request)

    def test_checking_the_fire_log_saves_nothing(self):
        response = self.post(FIRE_LOG)
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual((data['kind'], data['saved'], data['read'], data['new']), ('fire', False, 2, 1))
        self.assertEqual(data['problems'][0], {'label': 'Outside Talisay City', 'rows': ['row 5']})
        self.assertFalse(HistoricalRecord.objects.exists())

    def test_importing_adds_the_fires_once_and_is_logged(self):
        response = self.post(FIRE_LOG, save='true')
        self.assertEqual(response.status_code, 201)
        record = HistoricalRecord.objects.get()
        self.assertEqual((record.hazard_type, record.alarm_level, record.location_text),
                         (self.fire, '1ST ALARM', '12 RIZAL ST, BRGY HOME'))
        self.assertTrue(AuditLog.objects.filter(action='IMPORT_HISTORY', user=self.officer).exists())

        again = self.post(FIRE_LOG, save='true').data
        self.assertEqual((again['new'], again['already']), (0, 1))
        self.assertEqual(HistoricalRecord.objects.count(), 1)

    def test_the_flood_log_is_told_apart_by_its_sheets(self):
        response = self.post(FLOOD_LOG, save='true')
        self.assertEqual((response.status_code, response.data['kind'], response.data['new']),
                         (201, 'flood_landslide', 1))
        record = HistoricalRecord.objects.get()
        self.assertEqual((record.hazard_type, record.barangay, record.hazard_subcategory),
                         (self.flood, self.home, 'RIVER OVERFLOW'))

    def test_a_flood_log_missing_a_sheet_is_refused_not_read_as_fires(self):
        response = self.post(workbook_bytes({'Flood': HEADERS + [FLOOD_ROW]}))
        self.assertEqual(response.status_code, 400)
        self.assertIn('By Barangay', response.data['file'])

    def test_a_file_the_history_page_exported_is_refused(self):
        response = self.post(workbook_bytes({'History': HEADERS + [fire_row()]}))
        self.assertEqual(response.status_code, 400)
        self.assertIn('exported from the History page', response.data['file'])

    def test_only_an_excel_workbook(self):
        self.assertEqual(self.post(b'a,b', name='log.csv').status_code, 400)
        self.assertEqual(self.post(b'not really a workbook').data['file'], 'This is not an Excel workbook (.xlsx).')

    def test_drrmo_only(self):
        bfp = User.objects.create_user(email='bfp@test.ph', password='x', full_name='Fire Officer',
                                       role=Role.objects.get_or_create(name='BFP_Personnel')[0])
        self.assertEqual(self.post(FIRE_LOG, user=bfp, save='true').status_code, 403)
        self.assertEqual(self.post(FIRE_LOG, user=self.reporter, save='true').status_code, 403)
        self.assertFalse(HistoricalRecord.objects.exists())
