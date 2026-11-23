# Data attribution

The fire risk model's feature file, `fire_purok_features.csv` (written by
`manage.py build_fire_features`), is derived from these free sources, none of which needs an
account:

| Source | Used for | Licence |
|---|---|---|
| Microsoft Global ML Building Footprints (tile 132330002) | building count, density, footprint size, gaps and crowding | ODbL 1.0 |
| © OpenStreetMap contributors | roads, main roads, fire stations (road distance), coastline, rivers | ODbL 1.0 |
| ESA WorldCover 2021 v200 (© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium) | built-up, grass/shrub/bare and tree cover shares | CC BY 4.0 |
| WorldPop constrained population, 100 m (www.worldpop.org) | population, when a download without an account works (the meta file says which release, or that it was left out) | CC BY 4.0 |

The feature file's meta (`fire_purok_features.meta.json`) records the exact sources used for each
build.

The model's recipe is adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21
fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT License, © 2017 mmadaio).

The flood exposure (UP NOAH), storm days (IBTrACS), rain (NASA POWER) and Rain watch (NOAA GFS,
PAGASA) files were removed on 2026-11-22 with flood and landslide prediction and the Rain watch
(docs/design/specs/2026-11-22-fire-purok-model-design.md, Part A).
