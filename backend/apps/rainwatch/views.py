"""
The rain-watch API.

  GET  /api/rain-watch/                        the next 3 days' levels (anyone; Yellow only for DRRMO, admins)
  POST /api/rain-watch/forecast-runs/         the scheduled job posts one GFS run (bearer token)
  GET  /api/rain-watch/forecast-runs/status/   which recent runs the site already holds (same token)
  GET  /api/rain-watch/overrides/              active DRRMO overrides and the last 20 (DRRMO, admins)
  POST /api/rain-watch/overrides/              set a minimum colour by hand
  POST /api/rain-watch/overrides/<id>/cancel/  end one early (409 if already cancelled)
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rainwatch import assess
from apps.rainwatch.auth import IngestTokenPermission
from apps.rainwatch.models import RainForecastRun, RainForecastSeries, RainWatchOverride
from apps.rainwatch.serializers import ForecastRunSerializer, OverrideSerializer
from utils.permissions import IsDRRMOOfficer

STATUS_WINDOW = timedelta(days=3)


class RainWatchView(APIView):
    """Public. DRRMO officers and admins get every level and the staff lists; everyone else the public view."""
    permission_classes = [AllowAny]

    def get(self, request):
        role = getattr(request.user, 'role', None) if request.user.is_authenticated else None
        staff = role is not None and role.name in assess.STAFF_ROLES
        return Response(assess.rain_watch(staff=staff))


class TokenView(APIView):
    authentication_classes = []  # no session, so no CSRF
    permission_classes = [IngestTokenPermission]


def _store_series(run, points):
    RainForecastSeries.objects.bulk_create([
        RainForecastSeries(run=run, lat=p['lat'], lon=p['lon'], first_hour_start=p['first_hour_start'],
                           mm_per_hour=p['mm_per_hour'])
        for p in points])


class ForecastRunView(TokenView):
    """A new (source, init_time) is stored: 201 {"created": true}.

    The same run again is a no-op (200 {"created": false}), unless the stored one is shorter: the job
    re-fetches a newest run it holds short (a 6-hour gap-fill run), and keeping the short one would leave
    the site stale while the job reports success. Then its series, hours, job_version and received_at
    are replaced in one transaction (with update(), as the rows are otherwise insert-only):
    200 {"created": false, "upgraded": true}.
    """

    def post(self, request):
        serializer = ForecastRunSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        hours = len(data['points'][0]['mm_per_hour'])
        upgraded = False
        try:
            with transaction.atomic():
                run, created = RainForecastRun.objects.get_or_create(
                    source=data['source'], init_time=data['init_time'],
                    defaults={'job_version': data['job_version'], 'hours': hours})
                if created:
                    _store_series(run, data['points'])
                elif RainForecastRun.objects.select_for_update().get(pk=run.pk).hours < hours:
                    RainForecastSeries.objects.filter(run=run).delete()
                    _store_series(run, data['points'])
                    RainForecastRun.objects.filter(pk=run.pk).update(
                        hours=hours, job_version=data['job_version'], received_at=timezone.now())
                    upgraded = True
        except IntegrityError:  # the same run arrived twice at once
            created = False
        if created or upgraded:
            assess.bump()
        body = {'created': created, **({'upgraded': True} if upgraded else {})}
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ForecastRunStatusView(TokenView):
    def get(self, request):
        runs = (RainForecastRun.objects.filter(init_time__gte=timezone.now() - STATUS_WINDOW)
                .order_by('-init_time', 'source'))
        return Response({'runs': [
            {'source': r.source, 'init_time': r.init_time, 'hours': r.hours} for r in runs]})


RECENT_OVERRIDES = 20


class OverrideListView(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        base = RainWatchOverride.objects.select_related('created_by')
        now = timezone.now()
        active = list(base.filter(cancelled_at__isnull=True, starts_at__lte=now, ends_at__gt=now)
                      .order_by('-created_at', '-id'))
        recent = list(base.order_by('-created_at', '-id')[:RECENT_OVERRIDES])
        seen = {o.id for o in active}
        rows = active + [o for o in recent if o.id not in seen]
        return Response(OverrideSerializer(rows, many=True).data)

    def post(self, request):
        serializer = OverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        override = serializer.save(created_by=request.user)
        assess.bump()
        return Response(OverrideSerializer(override).data, status=status.HTTP_201_CREATED)


class OverrideCancelView(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request, pk):
        with transaction.atomic():
            override = get_object_or_404(RainWatchOverride.objects.select_for_update(), pk=pk)
            if override.cancelled_at is not None:
                return Response({'detail': 'Already cancelled.'}, status=status.HTTP_409_CONFLICT)
            override.cancelled_at = timezone.now()
            override.cancelled_by = request.user
            override.save(update_fields=['cancelled_at', 'cancelled_by'])
        assess.bump()
        return Response(OverrideSerializer(override).data)
