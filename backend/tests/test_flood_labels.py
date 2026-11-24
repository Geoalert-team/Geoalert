"""
The flood model's label sources (plan Task 1): the 2017 UP Mananga survey's
field points parsed from its Annex 11, distinct survey spots, and the
checksum-pinned downloads they come from. Nothing here touches the network.
"""
import hashlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.history.downloads import fetch_verified
from apps.history.flood_labels import parse_annex11, spots

FIXTURE = ('1 10.23583619 123.8315539 0.21 0.3 0.0081 Seniang 100-Year\n'
           'Hazard Mapping of the Philippines Using LIDAR (Phil-LIDAR 1)\n'
           '2  10.23583619   123.8315539 0.71 1.2 0.2401 Ruping  100-Year\n')


class StubResponse:
    def __init__(self, body):
        self.body = body
        self.status_code = 200

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]


class StubSession:
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return StubResponse(self.body)


class Annex11Tests(SimpleTestCase):
    def test_parse_rows_and_count_check(self):
        with self.assertRaisesMessage(ValueError, 'Annex 11 must have 169 rows, found 2.'):
            parse_annex11(FIXTURE)
        rows = parse_annex11(FIXTURE, expected=2)
        self.assertEqual(rows[0], {'point': 1, 'lat': 10.23583619, 'lon': 123.8315539, 'modelled_m': 0.21,
                                   'reported_m': 0.3, 'event': 'Seniang'})
        self.assertEqual(rows[1]['event'], 'Ruping')  # extra spaces are normalised

    def test_spots_merge_events_and_mark_positive(self):
        pts = [{'lat': 1.0, 'lon': 2.0, 'reported_m': 0.0, 'event': 'Ruby'},
               {'lat': 1.0, 'lon': 2.0, 'reported_m': 0.5, 'event': 'Seniang'},
               {'lat': 3.0, 'lon': 4.0, 'reported_m': 0.0, 'event': 'Ruby'}]
        s = {(x['lat'], x['lon']): x for x in spots(pts)}
        self.assertTrue(s[(1.0, 2.0)]['positive'])
        self.assertEqual(s[(1.0, 2.0)]['max_depth'], 0.5)
        self.assertEqual(s[(1.0, 2.0)]['events'], ['Ruby', 'Seniang'])
        self.assertFalse(s[(3.0, 4.0)]['positive'])


class DownloadTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_checksum_mismatch_keeps_nothing(self):
        with self.assertRaises(RuntimeError):
            fetch_verified('http://x', '0' * 64, self.tmp / 'f.pdf', session=StubSession(b'abc'))
        self.assertFalse((self.tmp / 'f.pdf').exists())
        self.assertFalse((self.tmp / 'f.part').exists())

    def test_a_good_download_is_kept_and_not_fetched_again(self):
        body = b'flood survey'
        session = StubSession(body)
        sha = hashlib.sha256(body).hexdigest()
        path = fetch_verified('http://x', sha, self.tmp / 'f.pdf', session=session)
        self.assertEqual(path.read_bytes(), body)
        fetch_verified('http://x', sha, self.tmp / 'f.pdf', session=session)
        self.assertEqual(session.calls, 1)

    def test_a_cached_file_with_the_wrong_checksum_is_refused(self):
        (self.tmp / 'f.pdf').write_bytes(b'changed')
        with self.assertRaises(RuntimeError):
            fetch_verified('http://x', '0' * 64, self.tmp / 'f.pdf', session=StubSession(b'x'))
