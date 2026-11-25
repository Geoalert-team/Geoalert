"""
manage.py build_landslide_training [--cache-dir DIR] [--output-dir DIR] [--events KEY ...]

Builds the landslide susceptibility model's training table from open landslide
inventories: NASA COOLR (points mapped after 2019-2023 rain events, Typhoon Egay
and Tropical Storms Paeng and Agaton among them) and the Typhoon Mangkhut scars
at Itogon (polygons, each placed at its highest cell). "No" points are sampled
around each event's slides (3 per slide, 60 m to 2 km away, seed 0). Every point
gets the clues of apps/history/landslide_features.py, computed on 12 km tiles
(Copernicus DEM, OpenStreetMap roads, Esri land cover of the year before the
event), and Philippine points the UP NOAH landslide class. Points at height 0
(sea or no data: the sea is not ground) and points missing a terrain clue are
dropped, counted per event.

The road check keeps an event's road distances only where its road density is at
least a tenth of Talisay's on steep ground; Talisay's extent comes from the
barangay outlines (read only).

Writes apps/history/data/landslide_training.csv (no coordinates; a database
derived from ODbL data) and landslide_training.meta.json. Downloads and each
finished tile go to the cache folder (backend/.hazard_cache), so a stopped run
resumes where it stopped. Rerun only if an inventory changes.

--events KEY ... runs a trial on those events only: no road check (and no
database), and the table goes to --output-dir, never over the committed one.
"""
import zipfile
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.barangays.models import Barangay
from apps.hazards import susceptibility as sus
from apps.history import landslide_features as lf
from apps.history import landslide_inventories as inv
from apps.history import landslide_sources as ls
from apps.history import landslide_training_table as lt

ZOOM = 14
CITY_PAD_M = 2000  # Talisay's grid, as build_landslide_features lays it
SCAR_PAD_M = 100   # around the Mangkhut scars, for the DEM their highest cells are read from
VALUE_COLUMNS = lf.FEATURE_COLUMNS + ('noah_class',)
# Bump when a saved tile's contents change meaning. 2: the sampling area is land only (R23);
# 3: a tile with no road has unknown (NaN) road distances.
TILE_VERSION = 3


def _tag(grid) -> str:
    return f'z{grid.zoom}_{grid.px0}_{grid.py0}_{grid.width}x{grid.height}'


class Command(BaseCommand):
    help = "Build the landslide model's training table from the open landslide inventories."

    def add_arguments(self, parser):
        parser.add_argument('--cache-dir', default=None,
                            help='Where downloads and finished tiles go (default backend/.hazard_cache).')
        parser.add_argument('--output-dir', default=None, help='Where the table goes (default apps/history/data).')
        parser.add_argument('--events', nargs='+', default=None, metavar='KEY',
                            help='Only these events, as a trial: no road check; needs --output-dir.')
        parser.add_argument('--philippines-only', action='store_true',
                            help='A real run over the Philippine typhoons only (road check kept); the world events '
                                 'are left out, so the world test cannot run.')
        parser.add_argument('--saved-tiles-only', action='store_true',
                            help='Use only tiles already saved in the cache; the points of any other tile are left '
                                 'out and counted (no download). Faster, with fewer rows.')

    def handle(self, *args, **options):
        cache = Path(options['cache_dir'] or Path(settings.BASE_DIR) / '.hazard_cache')
        only = options['events']
        if only and not options['output_dir']:
            raise CommandError('A trial (--events) writes its table to --output-dir, never over the committed one.')
        if only and options['philippines_only']:
            raise CommandError('--philippines-only is a real run; a trial (--events) already picks its events.')
        out = Path(options['output_dir'] or lf.TRAINING_FILE.parent)
        try:
            cache.mkdir(parents=True, exist_ok=True)
            self.build(cache, out, only, self.stdout.write, philippines_only=options['philippines_only'],
                       saved_tiles_only=options['saved_tiles_only'])
        except (RuntimeError, OSError, ValueError, zipfile.BadZipFile, requests.RequestException) as exc:
            raise CommandError(str(exc)) from exc

    def build(self, cache, out, only, log, philippines_only=False, saved_tiles_only=False):
        self.saved_only, self.left_out, self.done = saved_tiles_only, {}, {}  # ruling R59: no download
        coolr = inv.read_coolr(cache)
        events = inv.coolr_events(coolr)
        events[inv.MANGKHUT_EVENT.key] = inv.MANGKHUT_EVENT
        keys = [k for k in inv.EVENT_NOAH if k in events] + sorted(k for k, e in events.items() if e.region == 'world')
        if only:
            unknown = sorted(set(only) - set(events))
            if unknown:
                raise CommandError(f"Unknown events: {', '.join(unknown)}. Known: {', '.join(keys)}.")
            keys = [k for k in keys if k in only]
        world_left_out = []
        if philippines_only:  # ruling R57: the user's choice, to finish sooner; the world test then cannot run
            world_left_out = [k for k in keys if events[k].region == 'world']
            keys = [k for k in keys if events[k].region != 'world']
            log(f"Philippine typhoons only: {', '.join(keys)}. "
                f"World events left out: {', '.join(world_left_out) or 'none'}.")
        slides, outlines, repairs = {}, {}, {}
        for s in inv.coolr_slides(coolr):
            slides.setdefault(s['event'], []).append((s['lon'], s['lat']))
        if 'mangkhut' in keys:
            slides['mangkhut'], outlines['mangkhut'], repairs['mangkhut'] = self.mangkhut_scars(cache, log)

        talisay = None if only else self.talisay_steep_density(cache, log)

        built, densities, lc_read, lc_missing = {}, {}, 0, 0
        for key in keys:
            built[key], densities[key], (read, missing) = self.event_values(
                events[key], np.asarray(slides[key], float), cache, log, outlines.get(key))
            lc_read, lc_missing = lc_read + read, lc_missing + missing
        if lc_read and lc_missing:  # one failed read must not switch land cover off for the whole table
            raise CommandError(
                f'{lc_missing} of {lc_read + lc_missing} tiles have no land cover; rerun to resume (the tiles that '
                'read it are saved, so only these are tried again). If the land cover can no longer be read at '
                'all, delete both the saved tiles (landslide_tile_*.npz) and the saved land cover (lulc_*.npz) '
                'in the cache folder to build the table without it.')
        landcover_ok = lc_missing == 0
        kept = lt.road_check(densities, talisay) if talisay is not None else {k: None for k in keys}

        rows, events_meta = [], []
        for key in keys:
            ev, (label, values, ground) = events[key], built[key]
            # A missing terrain clue would grey every Talisay point (R20); the sea is not ground (R21).
            finite = np.all([np.isfinite(values[c]) for c in lf.TERRAIN_COLUMNS], axis=0)
            keep = finite & ground
            road_unknown = int((keep & np.isnan(values['dist_road_m'])).sum())  # on tiles with no road at all
            if kept[key] is False:
                values['dist_road_m'][:] = np.nan
            for i in np.flatnonzero(keep):
                row = {'event': key, 'fold': ev.fold, 'region': ev.region, 'label': int(label[i])}
                row.update({c: float(values[c][i]) for c in VALUE_COLUMNS})
                rows.append(row)
            n_slides, n_no = int(label[keep].sum()), int((label[keep] == 0).sum())
            done = self.done[key]  # False on a tile left out (--saved-tiles-only): not counted as dropped
            dropped, at_sea = int((~finite & done).sum()), int((finite & ~ground).sum())
            tiles_out, points_out = self.left_out.get(key, (0, 0))
            noah_zero = keep & (values['noah_class'] == 0)  # outside every listed province's hazard polygons
            zero_slides = int((noah_zero & (label == 1)).sum()) if ev.region == 'ph' else None
            zero_no = int((noah_zero & (label == 0)).sum()) if ev.region == 'ph' else None
            events_meta.append({'key': key, 'fold': ev.fold, 'region': ev.region, 'slides': n_slides,
                                'no_points': n_no, 'landcover_year': ev.landcover_year, 'road_kept': kept[key],
                                'dropped_missing_terrain': dropped, 'dropped_at_sea_level': at_sea,
                                'road_unknown': road_unknown, 'noah_zero_slides': zero_slides,
                                'noah_zero_no_points': zero_no,
                                'outlines_repaired': repairs.get(key, {}).get('repaired'),
                                'outlines_dropped': repairs.get(key, {}).get('dropped'),
                                'tiles_left_out': tiles_out, 'points_left_out': points_out})
            roads = {True: 'roads kept', False: 'roads dropped', None: 'roads not checked (trial)'}[kept[key]]
            noah = f'; NOAH class 0 at {zero_slides} slides and {zero_no} no points' if ev.region == 'ph' else ''
            log(f'{key}: {n_slides} slides, {n_no} no points, {roads} ({densities[key]:.3f} km/km²), '
                f'{road_unknown} on tiles with no road; {dropped} dropped for a missing terrain clue; '
                f'{at_sea} dropped at sea level{noah}')

        meta = {
            'built_at': timezone.localtime().isoformat(timespec='seconds'),
            'seed': lt.SEED,
            'landcover_ok': bool(landcover_ok),
            'talisay_steep_road_density': None if talisay is None else round(talisay, 4),
            'road_check': self.road_check_meta(talisay, densities),
            'world_left_out': world_left_out,
            'saved_tiles_only': bool(saved_tiles_only),
            'events': events_meta,
            'rows': len(rows),
            'sources': self.sources(keys, events),
        }
        path, meta_path = out / lf.TRAINING_FILE.name, out / lf.TRAINING_META.name
        lt.write_table(rows, meta, path, meta_path)

        missing = {c: sum(1 for r in rows if np.isnan(r[c])) for c in VALUE_COLUMNS}
        total_slides = sum(e['slides'] for e in events_meta)
        log(self.style.SUCCESS(f'Wrote {len(rows)} rows ({total_slides} slides, {len(rows) - total_slides} no points) '
                               f'from {len(keys)} events to {path}.'))
        log('Missing values: ' + (', '.join(f'{c} {n}' for c, n in missing.items() if n) or 'none'))
        log('Land cover read for every tile.' if landcover_ok else
            'Land cover could not be read for any tile; the model will not use it.')

    # --- Slides and tiles ----------------------------------------------------

    def mangkhut_scars(self, cache, log):
        """
        (the Mangkhut scars as points, each at its highest DEM cell; their outlines
        in WGS84, made valid once here so the scar points and the "no" points'
        union both read valid outlines; {'repaired': n, 'dropped': n}).
        """
        polys, repaired, dropped = lt.repair_outlines([p.transform(4326, clone=True) for p in inv.read_mangkhut(cache)])
        extents = np.array([p.extent for p in polys])
        grid, _ = sus.city_grid((extents[:, 0].min(), extents[:, 1].min(), extents[:, 2].max(), extents[:, 3].max()),
                                zoom=ZOOM, pad_m=SCAR_PAD_M)
        log(f'mangkhut: {len(polys)} scar outlines ({repaired} repaired, {dropped} with no area dropped), '
            'each placed at its highest cell')
        dem = ls.dem_for(grid, cache, log)
        return [lt.scar_point(p, grid, dem) for p in polys], polys, {'repaired': repaired, 'dropped': dropped}

    def event_values(self, ev, slides, cache, log, outlines=None):
        """
        ((label, {column: values}, on ground), road density, (tiles with land
        cover, tiles without)) for one event's points. `outlines`: its mapped slide
        polygons, which "no" points stay out of (Mangkhut).
        """
        nop = lt.event_no_points(slides, seed=lt.SEED, polygons=outlines)
        pts = np.r_[slides, nop]
        label = np.r_[np.ones(len(slides), int), np.zeros(len(nop), int)]
        values = {c: np.full(len(pts), np.nan) for c in VALUE_COLUMNS}
        ground = np.zeros(len(pts), bool)
        road_km = area_km2 = 0.0
        lc_read = lc_missing = 0
        tiles = lt.tiles_for(pts)
        log(f'{ev.key}: {len(slides)} slides and {len(nop)} no points on {len(tiles)} tiles')
        done, tiles_out = np.zeros(len(pts), bool), 0
        for n, tile in enumerate(tiles, 1):
            log(f'  Tile {n} of {len(tiles)}')
            part = self.tile_values(ev, tile, pts, slides, cache, log)
            if part is None:  # --saved-tiles-only and this tile is not saved: its points are left out
                tiles_out += 1
                continue
            done[tile['index']] = True
            for c in VALUE_COLUMNS:
                values[c][tile['index']] = part[c]
            ground[tile['index']] = part['on_ground']
            road_km += float(part['road_km'])
            area_km2 += float(part['area_km2'])
            if bool(part['landcover_ok']):
                lc_read += 1
            else:
                lc_missing += 1
        density = road_km / area_km2 if area_km2 > 0 else 0.0
        self.done[ev.key] = done
        if tiles_out:
            self.left_out[ev.key] = (tiles_out, int((~done).sum()))
            log(f'{ev.key}: {tiles_out} of {len(tiles)} tiles not saved, left out ({int((~done).sum())} points)')
        return (label, values, ground), density, (lc_read, lc_missing)

    def tile_values(self, ev, tile, pts, slides, cache, log):
        """
        The clues at the tile's points and its road length and area inside the
        event's sampling area; saved when complete (land cover read), so a
        rerun resumes. A saved tile is used only when its points, TILE_VERSION
        and the event's NOAH provinces match.
        """
        grid = sus.Grid(*tile['bbox_outer'], ZOOM)
        here = pts[tile['index']]
        provinces = np.asarray(ev.noah_provinces, dtype=str)
        saved = Path(cache) / f'landslide_tile_{ev.key}_{_tag(grid)}.npz'
        z = ls.read_saved(saved, ls.npz_arrays, log)  # a tile a stopped run left cut short is deleted and rebuilt
        if z is not None and ('version' in z and int(z['version']) == TILE_VERSION
                              and 'noah_provinces' in z and np.array_equal(z['noah_provinces'], provinces)
                              and np.array_equal(z['points'], here)):
            log('  Using saved tile')
            return z
        if getattr(self, 'saved_only', False):
            log('  Not saved; left out (--saved-tiles-only)')
            return None
        try:
            dem = ls.dem_for(grid, cache, log)
        except RuntimeError as exc:
            if str(exc) != sus.NO_HEIGHT:
                raise
            log('  No ground above sea level on this tile; its points read as sea')
            dem = np.zeros(grid.shape, np.float32)
        log('  Terrain clues...')
        grids = lf.terrain_grids(dem, grid.res)
        roads = ls.roads(tile['bbox_outer'], cache, log)
        if roads:
            grids['dist_road_m'] = lf.road_distance(grid, roads)
        else:  # no road on the tile: unknown, not the 10,000 km placeholder distance_to gives an empty mask
            log('  No road on this tile; its road distances are unknown')
            grids['dist_road_m'] = np.full(grid.shape, np.nan, np.float32)
        classes = ls.landcover_classes(grid, ev.landcover_year, cache, log)
        if classes is not None:
            grids.update(lf.landcover_shares(classes, grid.res))
        else:
            grids.update({name: np.full(grid.shape, np.nan, np.float32) for name in lf.LANDCOVER_CLASSES.values()})
        if ev.noah_provinces:
            grids['noah_class'] = ls.noah_landslide_grid(grid, ev.noah_provinces, cache, log)
        else:
            grids['noah_class'] = np.full(grid.shape, np.nan, np.float32)  # NOAH maps the Philippines only
        grids['height'] = dem
        sampled = lf.sample(grid, grids, here)

        area = lt.sampling_area(grid, slides, tile['bbox_inner'], dem)  # land only, as Talisay's steep cells are
        area_km2 = float(area.sum() * grid.res ** 2 / 1e6)
        part = {c: np.asarray(sampled[c], float) for c in VALUE_COLUMNS}
        part.update(points=here, on_ground=np.asarray(sampled['height']) > 0, area_km2=area_km2,
                    road_km=ls.road_density_km_per_km2(grid, roads, area) * area_km2,
                    landcover_ok=classes is not None, version=TILE_VERSION, noah_provinces=provinces)
        if classes is not None:  # a tile without land cover is tried again next run
            ls.save_atomically(saved, lambda f: np.savez_compressed(f, **part))  # whole or not at all
        return part

    # --- The road check ------------------------------------------------------

    def talisay_steep_density(self, cache, log):
        """Talisay's km of road per km² on city cells of STEEP_DEG or steeper, on build_landslide_features' grid."""
        barangays = list(Barangay.objects.exclude(boundary__isnull=True))
        if not barangays:
            raise CommandError('No barangay outlines are loaded; the road check needs them. Load them first.')
        polygons = []
        west = south = float('inf')
        east = north = float('-inf')
        for b in barangays:
            x0, y0, x1, y1 = b.boundary.extent
            west, south, east, north = min(west, x0), min(south, y0), max(east, x1), max(north, y1)
            for poly in b.boundary:
                polygons.append((b.id, [list(ring.coords) for ring in poly]))
        grid, bbox = sus.city_grid((west, south, east, north), zoom=ZOOM, pad_m=CITY_PAD_M)
        log(f'Talisay, for the road check: grid {grid.width} x {grid.height}')
        dem = ls.dem_for(grid, cache, log)
        roads = ls.roads(bbox, cache, log)
        city = sus.draw_polygons(grid, polygons) > 0
        log('  Terrain clues (the sink fill takes a minute)...')
        slope = lf.terrain_grids(dem, grid.res)['slope_deg']
        density = ls.road_density_km_per_km2(grid, roads, city & (slope >= lt.STEEP_DEG))
        if density <= 0:
            raise CommandError(f'Talisay shows no road on ground of {lt.STEEP_DEG} degrees or steeper; '
                               'the road check cannot run.')
        log(f'  {density:.3f} km of road per km² on ground of {lt.STEEP_DEG} degrees or steeper')
        return density

    @staticmethod
    def road_check_meta(talisay, densities):
        dens = {k: round(v, 4) for k, v in densities.items()}
        if talisay is None:
            return {'skipped': 'trial run (--events): the road check needs Talisay\'s outlines', 'events': dens}
        return {'talisay_steep_road_density': round(talisay, 4), 'steep_deg': lt.STEEP_DEG,
                'share': lt.ROAD_SHARE, 'threshold': round(lt.ROAD_SHARE * talisay, 4), 'events': dens}

    @staticmethod
    def sources(keys, events):
        out = {
            'coolr': {'url': inv.COOLR_URL, 'sha256': inv.COOLR_SHA256, 'licence': 'CC BY 4.0'},
            'elevation': {'url': sus.COPERNICUS_URL, 'sha256': None, 'licence': 'Copernicus DEM licence',
                          'notice': sus.COPERNICUS_NOTICE},
            'landcover': {'url': ls.LANDCOVER_URL, 'sha256': None, 'licence': 'CC BY 4.0'},
            'roads': {'url': list(sus.OVERPASS_URLS), 'sha256': None, 'licence': 'ODbL'},
        }
        if 'mangkhut' in keys:
            out['mangkhut'] = {'url': inv.MANGKHUT_URL, 'sha256': dict(inv.MANGKHUT_FILES),
                               'licence': 'Open Government Licence'}
        provinces = sorted({p for k in keys for p in events[k].noah_provinces})
        if provinces:
            out['noah'] = {p: {'url': ls.NOAH_URL.format(province=p), 'sha256': ls.NOAH_LANDSLIDE[p], 'licence': 'ODbL'}
                           for p in provinces}
        return out
