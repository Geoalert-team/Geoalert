"""
Sample hazards for Talisay City, generated with Faker.

Replaces the hand-written pins that used to live in the frontend. Events are
placed the way Project NOAH's hazard maps would predict them: each one lands
on a cell the susceptibility rasters (build_hazard_index) rate as
susceptible to that hazard, with the highest classes picked most often and given
the worst severities. Floods therefore gather on the low coastal plain and
along the rivers, landslides on the upland slopes, and fires in the dense
built-up blocks. Dates follow Talisay's seasons: floods and landslides peak
with the typhoons from September to December, fires in the dry months of
March to May.

Everything here is pure (no database), so it can be tested on its own; the
seed_fake_hazards command turns the results into rows.
"""
import bisect
import itertools
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

HAZARDS = ('Flood', 'Landslide', 'Fire')
LAYER = {'Flood': 'flood', 'Landslide': 'landslide', 'Fire': 'fire'}

# Relative chance of an event in each month, January first
MONTH_WEIGHTS = {
    'Flood':     [0.6, 0.4, 0.3, 0.3, 0.6, 1.0, 1.3, 1.3, 1.4, 1.6, 1.8, 1.5],
    'Landslide': [1.0, 0.6, 0.3, 0.3, 0.5, 0.8, 1.0, 1.1, 1.2, 1.5, 1.8, 1.6],
    'Fire':      [1.0, 1.2, 1.8, 1.9, 1.5, 0.7, 0.6, 0.6, 0.6, 0.7, 0.8, 1.2],
}

# Typical events per year in the archive
EVENTS_PER_YEAR = {'Flood': 10, 'Landslide': 4, 'Fire': 12}

# Typhoons each year bring several floods and landslides on the same days
STORMS_PER_YEAR = (1, 2)
STORM_MONTHS = (9, 10, 11, 12)
STORM_EVENTS = (3, 7)

# Only cells at or above this susceptibility class can host an event;
# higher classes are picked more often. Fire starts at Low because few
# buildings are mapped in OpenStreetMap here, so the built-up blocks mostly
# score Low and Medium-or-higher alone would favor a few upland patches.
MIN_CLASS = {'Flood': 3, 'Landslide': 3, 'Fire': 2}
CLASS_WEIGHT = {2: 1.0, 3: 3.0, 4: 6.0, 5: 10.0}

# Chance of Red / Orange / Green by the susceptibility class of the spot
SEVERITY_ODDS = {
    3: (0.10, 0.30, 0.60),
    4: (0.25, 0.50, 0.25),
    5: (0.50, 0.40, 0.10),
}
SEVERITIES = ('Red', 'Orange', 'Green')

# ---------------------------------------------------------------------------
# Size and toll of one event. The zone radius is worked out first and the
# houses, people and wording follow from it, so a kitchen fire is never
# drawn as large as a river overflow.
# ---------------------------------------------------------------------------

# Fire: the zone is the burned block plus the cordon around it. A closely
# built neighborhood has about 60 m2 of ground per house (30-40 m2 of floor
# at ~60% coverage), so 40 razed houses burn ~0.25 ha, a ~27 m radius.
GROUND_PER_HOUSE_M2 = 60
FIRE_HOUSES = {'Red': (12, 250), 'Orange': (1, 8)}  # drawn log-uniform: most fires are small
FIRE_CORDON_M = {'Red': (20, 30), 'Orange': (12, 20)}
FIRE_GREEN_RADIUS_M = (8, 20)  # grass or kitchen fire, no house lost
FAMILIES_PER_HOUSE = (1.0, 1.5)  # shared houses are common in informal areas
HOUSEHOLD_SIZE = 4.1  # PSA 2020 average household

# Floods and landslides: radius of the affected zone in meters
ZONE_RADIUS_M = {
    'Flood': {'Red': (250, 700), 'Orange': (120, 300), 'Green': (40, 120)},  # river overflow .. street ponding
    'Landslide': {'Red': (60, 150), 'Orange': (25, 60), 'Green': (10, 25)},  # the slide plus houses below it
}

# Floods: people living in the zone, and the share who actually evacuate
LOWLAND_PEOPLE_PER_M2 = 0.01  # ~10,000 per km2 on Talisay's coastal plain
FLOOD_EVACUATE = {'Red': (0.05, 0.20), 'Orange': (0.01, 0.05), 'Green': (0, 0)}

# Landslides: houses inside the danger zone, which are evacuated
LANDSLIDE_HOUSES = {'Red': (3, 25), 'Orange': (0, 6), 'Green': (0, 0)}

# (chance of any deaths or injuries, fewest, most) when there are some
CASUALTY_ODDS = {
    'Flood':     {'Red': (0.20, 1, 4), 'Orange': (0.03, 1, 1)},
    'Landslide': {'Red': (0.35, 1, 6), 'Orange': (0.05, 1, 1)},
    'Fire':      {'Red': (0.25, 1, 3), 'Orange': (0.05, 1, 1)},
}
NOT_COUNTED_ODDS = 0.15  # "nobody counted" is kept apart from zero

FLOOD_DEPTH_CM = {'Red': (70, 150), 'Orange': (30, 60), 'Green': (10, 25)}

# Faker's PH street formats, minus the American-sounding surname and "93rd" ones
STREET_FORMATS = (
    '{{plant_name}} {{street_suffix}}',
    '{{mountain_name}} {{street_suffix}}',
    '{{gemstone_name}} {{street_suffix}}',
)

DESCRIPTIONS = {
    'Flood': {
        'Red': [
            'River overflowed near {street} after {hours} hours of heavy rain; water about {depth} cm deep. '
            '{displaced} residents moved to evacuation centers.',
            'Waist-deep floodwater across low-lying blocks around {street}. '
            'Pre-emptive evacuation of {displaced} residents.',
        ],
        'Orange': [
            'Knee-deep water, about {depth} cm, on {street} as drainage backed up. '
            'Light vehicles advised to avoid the area.',
            'Floodwater around {depth} cm on low-lying lots near {street}. '
            'Residents moving belongings to higher floors.',
        ],
        'Green': [
            'Ankle-deep ponding on {street} after an afternoon thunderstorm. Passable to all vehicles.',
            'Minor flooding, about {depth} cm, on a stretch of {street}; drainage clearing requested from the city.',
        ],
    },
    'Landslide': {
        'Red': [
            'Slope failure about {width} m wide above {street} after {hours} hours of rain. '
            '{houses} houses below the slope evacuated.',
            'Soil movement near {street} with widening tension cracks. '
            '{houses} houses inside the danger zone evacuated.',
        ],
        'Orange': [
            'Soil and rocks slid onto {street}, blocking one lane. Slope being monitored for further movement.',
            'Cracks seen on the hillside near {street} after continuous rain. Nearby households told to stay alert.',
        ],
        'Green': [
            'Small rockfall on the road shoulder near {street}. Cleared by the barangay.',
            'Minor soil erosion along the slope beside {street}. No houses affected.',
        ],
    },
    'Fire': {
        'Red': [
            'Fire razed {houses} houses in a closely built block near {street}, leaving {families} families homeless. '
            'Reached {alarm} alarm before it was controlled.',
            'Residential fire near {street} spread through light-material houses; '
            '{houses} houses lost and {families} families affected.',
        ],
        'Orange': [
            'House fire near {street} damaged {houses} {house_word} before responders contained it.',
            'Fire on {street} gutted {houses} {house_word}; neighboring structures cooled to stop the spread.',
        ],
        'Green': [
            'Grass fire on a vacant lot near {street}, put out within the hour.',
            'Small kitchen fire on {street}, contained by residents before responders arrived.',
        ],
    },
}


# ---------------------------------------------------------------------------
# Susceptibility rasters
# ---------------------------------------------------------------------------

def _hex_rgb(color):
    n = int(color[1:], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


class SusceptibilityGrid:
    """One hazard's susceptibility PNG read back into classes 0 (outside the city) to 5."""

    def __init__(self, classes, width, height, bounds):
        self.classes = classes  # bytes, row by row
        self.width = width
        self.height = height
        (self.south, self.west), (self.north, self.east) = bounds
        self.y0 = self._merc_y(self.north)
        self.y1 = self._merc_y(self.south)

    @classmethod
    def from_png(cls, path, bounds, palette):
        img = Image.open(path).convert('RGBA')
        lookup = {(*_hex_rgb(c['color']), 255): i for i, c in enumerate(palette, start=1)}
        classes = bytes(lookup.get(px, 0) for px in img.getdata())
        return cls(classes, img.width, img.height, bounds)

    @staticmethod
    def _merc_y(lat):
        s = math.sin(math.radians(lat))
        return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)

    def to_lnglat(self, x, y):
        """Pixel position (may be fractional) -> (lng, lat). The raster is Web Mercator aligned."""
        lng = self.west + x / self.width * (self.east - self.west)
        m = self.y0 + y / self.height * (self.y1 - self.y0)
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * m))))
        return lng, lat

    def class_at(self, lng, lat):
        x = int((lng - self.west) / (self.east - self.west) * self.width)
        y = int((self._merc_y(lat) - self.y0) / (self.y1 - self.y0) * self.height)
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.classes[y * self.width + x]
        return 0


def load_grids(index_dir):
    """{'Flood': SusceptibilityGrid, ...} from the folder build_hazard_index writes."""
    index_dir = Path(index_dir)
    index = json.loads((index_dir / 'index.json').read_text())
    return {
        hazard: SusceptibilityGrid.from_png(index_dir / index['layers'][LAYER[hazard]], index['bounds'], index['classes'])
        for hazard in HAZARDS
    }


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

class Spots:
    """Draws event locations from one grid, weighted toward the most susceptible cells."""

    def __init__(self, grid, rnd, min_class=3):
        self.grid = grid
        self.rnd = rnd
        self.cells = [i for i, k in enumerate(grid.classes) if k >= min_class]
        if not self.cells:
            raise ValueError(f'No cells of susceptibility class {min_class} or higher to place events on.')
        self.cum = list(itertools.accumulate(CLASS_WEIGHT[grid.classes[i]] for i in self.cells))

    def draw(self):
        """(lng, lat, susceptibility class) of a random spot."""
        pick = bisect.bisect_right(self.cum, self.rnd.uniform(0, self.cum[-1]))
        i = self.cells[min(pick, len(self.cells) - 1)]
        y, x = divmod(i, self.grid.width)
        lng, lat = self.grid.to_lnglat(x + self.rnd.random(), y + self.rnd.random())
        return lng, lat, self.grid.classes[i]


def pick_severity(susceptibility_class, rnd):
    odds = SEVERITY_ODDS[min(max(susceptibility_class, 3), 5)]
    return rnd.choices(SEVERITIES, weights=odds)[0]


def pick_month(hazard, rnd):
    return rnd.choices(range(1, 13), weights=MONTH_WEIGHTS[hazard])[0]


def random_moment_in_month(year, month, rnd, now):
    """A datetime in that month, never later than now; None if the month hasn't started."""
    start = datetime(year, month, 1, tzinfo=now.tzinfo)
    if start > now:
        return None
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=now.tzinfo)
    end = min(end, now)
    return start + timedelta(seconds=rnd.uniform(0, (end - start).total_seconds()))


def _log_uniform_int(low, high, rnd):
    return int(round(math.exp(rnd.uniform(math.log(low), math.log(high)))))


def _alarm(houses):
    """BFP alarm level a fire of this size usually reaches."""
    return 'second' if houses < 20 else 'third' if houses < 60 else 'fourth' if houses < 150 else 'fifth'


def impact(hazard, severity, rnd):
    """
    Zone radius and toll of one event, consistent with each other:
    {'radius_m', 'casualties', 'displaced', 'details': values for the description}
    """
    details = {'hours': rnd.randint(3, 14)}
    displaced = 0

    if hazard == 'Fire':
        if severity == 'Green':
            radius = rnd.uniform(*FIRE_GREEN_RADIUS_M)
        else:
            houses = _log_uniform_int(*FIRE_HOUSES[severity], rnd)
            burned = math.sqrt(houses * GROUND_PER_HOUSE_M2 / math.pi)
            radius = burned + rnd.uniform(*FIRE_CORDON_M[severity])
            families = round(houses * rnd.uniform(*FAMILIES_PER_HOUSE))
            displaced = round(families * HOUSEHOLD_SIZE)
            details.update(houses=houses, families=families, alarm=_alarm(houses),
                           house_word='house' if houses == 1 else 'houses')
    elif hazard == 'Flood':
        radius = rnd.uniform(*ZONE_RADIUS_M['Flood'][severity])
        residents = math.pi * radius ** 2 * LOWLAND_PEOPLE_PER_M2
        displaced = round(residents * rnd.uniform(*FLOOD_EVACUATE[severity]))
        details.update(depth=rnd.randint(*FLOOD_DEPTH_CM[severity]), displaced=f'{displaced:,}')
    else:
        radius = rnd.uniform(*ZONE_RADIUS_M['Landslide'][severity])
        houses = rnd.randint(*LANDSLIDE_HOUSES[severity])
        displaced = round(houses * HOUSEHOLD_SIZE)
        details.update(houses=houses, width=max(10, int(round(radius * 0.6, -1))))

    casualties = 0
    odds = CASUALTY_ODDS[hazard].get(severity)
    if odds and rnd.random() < odds[0]:
        casualties = rnd.randint(odds[1], odds[2])

    def counted(n):
        return None if rnd.random() < NOT_COUNTED_ODDS else n

    return {
        'radius_m': round(radius),
        'casualties': counted(casualties),
        'displaced': counted(displaced),
        'details': details,
    }


def describe(hazard, severity, details, fake):
    template = fake.random_element(DESCRIPTIONS[hazard][severity])
    return template.format(street=fake.parse(fake.random_element(STREET_FORMATS)), **details)


def circle_ring(lng, lat, radius_m, sides=32):
    """Closed (lng, lat) ring approximating a circle, like the publish form draws."""
    dlat = radius_m / 111320
    dlng = dlat / math.cos(math.radians(lat))
    ring = [
        (lng + dlng * math.cos(2 * math.pi * k / sides), lat + dlat * math.sin(2 * math.pi * k / sides))
        for k in range(sides)
    ]
    return ring + [ring[0]]


def _event(hazard, spots, rnd, fake, when, storm=None, min_class=None, at=None):
    lng, lat, k = at if at else spots.draw()
    if min_class:
        k = max(k, min_class)  # a typhoon pushes every event at least this hard
    # Rated against the hazard's own starting class, so Low fire ground counts like Medium flood ground
    severity = pick_severity(k + 3 - MIN_CLASS[hazard], rnd)
    size = impact(hazard, severity, rnd)
    description = describe(hazard, severity, size['details'], fake)
    if storm:
        description = f'During tropical storm "{storm}". {description}'
    return {
        'hazard': hazard,
        'severity': severity,
        'lng': lng,
        'lat': lat,
        'radius_m': size['radius_m'],
        'occurred_at': when,
        'description': description,
        'casualties': size['casualties'],
        'displaced': size['displaced'],
    }


def historical_events(spots, years, now, fake, rnd):
    """
    Past events over the last `years` years, oldest first. Each has the
    occurrence time and a resolved time a few hours to days later.
    spots: {'Flood': Spots, ...}
    """
    events = []
    first_year = now.year - years + 1

    for year in range(first_year, now.year + 1):
        # Background events, spread over the year by season
        for hazard in HAZARDS:
            n = max(0, round(rnd.gauss(EVENTS_PER_YEAR[hazard], EVENTS_PER_YEAR[hazard] ** 0.5)))
            for _ in range(n):
                when = random_moment_in_month(year, pick_month(hazard, rnd), rnd, now)
                if when:
                    events.append(_event(hazard, spots[hazard], rnd, fake, when))

        # Typhoons: several floods and landslides across the city within a day or two
        for _ in range(rnd.randint(*STORMS_PER_YEAR)):
            landfall = random_moment_in_month(year, rnd.choice(STORM_MONTHS), rnd, now)
            if not landfall:
                continue
            storm = fake.first_name()
            for _ in range(rnd.randint(*STORM_EVENTS)):
                hazard = rnd.choices(('Flood', 'Landslide'), weights=(3, 1))[0]
                when = min(landfall + timedelta(hours=rnd.uniform(0, 36)), now)
                events.append(_event(hazard, spots[hazard], rnd, fake, when, storm=storm, min_class=4))

    for e in events:
        _set_resolved(e, now, rnd)

    events.sort(key=lambda e: e['occurred_at'])
    return events


def _set_resolved(event, now, rnd):
    hours = {'Red': (12, 96), 'Orange': (6, 48), 'Green': (2, 12)}[event['severity']]
    event['resolved_at'] = min(event['occurred_at'] + timedelta(hours=rnd.uniform(*hours)), now)


def past_event_near(hazard, lng, lat, grid, years, now, fake, rnd, spread_m=300):
    """
    One past event of this hazard within spread_m of (lng, lat), on ground that
    is prone to it when possible, dated in the hazard's season within the last
    `years` years. Used to give every active hazard's area a history.
    """
    min_class = MIN_CLASS[hazard]
    dlat = spread_m / 111320
    dlng = dlat / math.cos(math.radians(lat))
    for _ in range(15):
        plng = lng + rnd.uniform(-dlng, dlng)
        plat = lat + rnd.uniform(-dlat, dlat)
        k = grid.class_at(plng, plat)
        if k >= min_class:
            break
    else:
        plng, plat, k = lng, lat, max(grid.class_at(lng, lat), min_class)

    when = None
    while when is None:
        year = rnd.randint(now.year - years + 1, now.year)
        when = random_moment_in_month(year, pick_month(hazard, rnd), rnd, now)
    # Not in the last two weeks, so it reads as a past event rather than the current one
    when = min(when, now - timedelta(days=14))

    event = _event(hazard, None, rnd, fake, when, at=(plng, plat, k))
    _set_resolved(event, now, rnd)
    return event


def active_events(spots, count, now, fake, rnd):
    """Hazards still active on the map, with a type mix that fits the current month."""
    weights = [MONTH_WEIGHTS[h][now.month - 1] * EVENTS_PER_YEAR[h] for h in HAZARDS]
    events = []
    for _ in range(count):
        hazard = rnd.choices(HAZARDS, weights=weights)[0]
        when = now - timedelta(hours=rnd.uniform(1, 6 * 24))
        events.append(_event(hazard, spots[hazard], rnd, fake, when))
    return events
