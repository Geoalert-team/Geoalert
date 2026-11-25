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

## Flood susceptibility model

The flood model's feature file, `flood_purok_features.csv` (written by
`manage.py build_flood_features`), is derived from these free sources, none of which needs an
account:

| Source | Used for | Licence |
|---|---|---|
| UP NOAH flood hazard maps, 5- and 25-year (Cebu), via the bettergovph mirror on Hugging Face | flood depth class at each building; the 100-year map is only checked, never an input | ODbL 1.0 |
| Copernicus GLO-30 DEM: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved | height above the nearest river, sink depth | Copernicus DEM licence |
| © OpenStreetMap contributors | river centrelines | ODbL 1.0 |
| ESA WorldCover 2021 v200 | built-up share within 100 m | CC BY 4.0 |
| Microsoft Global ML Building Footprints (tile 132330002) | where the buildings are | ODbL 1.0 |

The model is trained (`manage.py train_flood_model`) on where floods were seen, kept private in the
git-ignored `backend/.hazard_cache` and never shown or redistributed; only fitted numbers reach the
website:

- Flood survey points: E. C. Paringit and R. S. Otadoy (eds.) (2017), *LiDAR Surveys and Flood
  Mapping of Mananga River*, UP Training Center for Applied Geodesy and Photogrammetry / University
  of San Carlos (Phil-LiDAR 1), Annex 11; used for research and education with acknowledgement.
- Tino flood proxy map (test only): Earth Observatory of Singapore – Remote Sensing Lab (EOS-RS);
  contains modified Copernicus Sentinel data (2025).

## Landslide susceptibility model

The landslide model's training table, `landslide_training.csv` (written by
`manage.py build_landslide_training`; one row per landslide or "no landslide" point with its clues,
no coordinates), and Talisay's clues (`manage.py build_landslide_features`) are derived from these
free sources, none of which needs an account (the building footprints are used for Talisay only):

- Landslide inventories: NASA Cooperative Open Online Landslide Repository, Vershel et al. (2025), Open inventories of rainfall-triggered landslides, Figshare doi 10.6084/m9.figshare.26972467 (CC BY 4.0)
- Abancó, C.; Jones, J.N. (2023). Areas affected by landslides following Typhoon Mangkhut in Itogon, Philippines, September 2018. NERC EDS Environmental Information Data Centre. doi 10.5285/32765a61-8510-4dfc-b7c7-58bad12f8497 (Open Government Licence)
- UP NOAH landslide hazard maps (ODbL), via the bettergovph mirror
- Esri / Impact Observatory 10 m annual land cover (CC BY 4.0)
- Copernicus GLO-30 DEM: produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved
- © OpenStreetMap contributors (ODbL)
- Microsoft building footprints (ODbL)

This table is a database derived from ODbL data and is shared under the ODbL. Its first line
carries the same notice. The table's meta (`landslide_training.meta.json`) records each source's
address, checksum and licence for the build.
