"""Country and region mask helpers."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def normalize_country_names(country_list: str | Iterable[str]) -> list[str]:
    """Normalize comma/semicolon separated country names to a clean list."""

    if isinstance(country_list, str):
        raw = [country_list]
    else:
        raw = list(country_list)

    names: list[str] = []
    for item in raw:
        for part in str(item).replace(";", ",").split(","):
            part = part.strip()
            if part:
                names.append(part)
    return names


def classify_countries_matrix(latitudes, longitudes, country_list) -> np.ndarray:
    """Return a boolean `(lat, lon)` mask for grid-cell centers in countries."""

    names = normalize_country_names(country_list)
    if not names:
        raise ValueError("At least one country name is required")

    import cartopy.io.shapereader as shpreader
    import shapely.geometry as sgeom
    from shapely.prepared import prep

    reader = shpreader.Reader(
        shpreader.natural_earth(
            resolution="110m",
            category="cultural",
            name="admin_0_countries",
        )
    )

    polygons = []
    for record in reader.records():
        record_names = {
            str(record.attributes.get(key, ""))
            for key in ("NAME", "ADMIN", "NAME_LONG")
        }
        if record_names.intersection(names):
            geom = record.geometry
            if geom.geom_type == "Polygon":
                polygons.append(geom)
            elif geom.geom_type == "MultiPolygon":
                polygons.extend(list(geom.geoms))

    if not polygons:
        raise ValueError(f"No Natural Earth polygons found for countries: {names}")

    region = prep(sgeom.MultiPolygon(polygons))
    latitude_values = np.asarray(latitudes)
    longitude_values = np.asarray(longitudes)
    if latitude_values.ndim == 2 and longitude_values.ndim == 2:
        if latitude_values.shape != longitude_values.shape:
            raise ValueError("2D latitude and longitude arrays must have the same shape")
        lat_grid = latitude_values
        lon_grid = longitude_values
    else:
        lon_grid, lat_grid = np.meshgrid(longitude_values, latitude_values)
    points = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
    mask = np.array([region.covers(sgeom.Point(x, y)) for x, y in points], dtype=bool)
    return mask.reshape(lon_grid.shape)
