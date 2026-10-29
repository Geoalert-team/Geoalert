"""
POST /api/history/import/: DRRMO brings the BFP fire log or the flood and
landslide log into the history from the History page, as manage.py
import_bfp_fires and import_flood_landslide do (apps/history/importing.py).

  file              the .xlsx; which log it is comes from its sheets
  save              'true' to import; anything else only checks the file
  include_warnings  'true' to also import the flood log's warnings-only rows

The page checks first and shows what would happen, then sends the same file
again with save. Re-planned on save rather than remembered, so the import
matches the history as it is then. Answers summary() either way, with
'saved'. Only rows not already imported are added; the command line keeps
--replace, which deletes records, off the page.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.history.importing import FIRE, ImportProblem, import_fires, import_floods, kind_of, summary
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer
from utils.sampling import TRUTHY

MAX_BYTES = 10 * 1024 * 1024


class HistoryImportView(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'file': 'Choose the .xlsx file to import.'}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith('.xlsx'):
            return Response({'file': 'Only Excel workbooks (.xlsx) can be imported.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if upload.size > MAX_BYTES:
            return Response({'file': 'The file is over 10 MB.'}, status=status.HTTP_400_BAD_REQUEST)
        save = (request.data.get('save') or '').lower() in TRUTHY
        warnings = (request.data.get('include_warnings') or '').lower() in TRUTHY

        try:
            kind = kind_of(upload)
            report = (import_fires(upload, save=save) if kind == FIRE
                      else import_floods(upload, save=save, include_warnings=warnings))
        except ImportProblem as e:
            return Response({'file': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        result = summary(kind, report)
        if save:
            log_event(request, 'IMPORT_HISTORY', 'historical_record', '',
                      f'{result["kind_label"]} imported from {upload.name}: {result["new"]} new record(s), '
                      f'{result["already"]} already in the history.'[:300])
        return Response({**result, 'saved': save},
                        status=status.HTTP_201_CREATED if save else status.HTTP_200_OK)
