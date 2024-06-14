import pandas as pd
import geopandas as gpd
import numpy as np
import osmnx as ox
from osmnx.features import InsufficientResponseError
from tqdm import tqdm
from shapely import Polygon,MultiPolygon
import shapely


def fetch_territory(territory_name):

    territory = ox.geocode_to_gdf(territory_name)
    territory = territory.set_crs(4326)
    territory = territory["geometry"].reset_index(drop=True)
    territory = gpd.GeoDataFrame(territory.make_valid(),columns=['geometry'])

    return territory


def fetch_buildings(territory, express_mode=True):

    if type(territory) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        territory = territory.unary_union

    buildings = ox.features_from_polygon(territory, tags={"building": True})
    buildings = buildings.loc[buildings["geometry"].type == "Polygon"]

    if not express_mode:
        buildings_ = ox.features_from_polygon(territory, tags={"building": "yes"})
        buildings_ = buildings_.loc[buildings_["geometry"].type == "Polygon"]["geometry"]
        buildings = gpd.GeoSeries(pd.concat([buildings, buildings_], ignore_index=True)).drop_duplicates()

    try:
        buildings = buildings[["geometry", "building:levels"]].reset_index(drop=True).rename(columns={"building:levels": "levels"})
    except:
        buildings = buildings["geometry"].reset_index(drop=True)

    buildings = gpd.GeoDataFrame(buildings)

    return buildings


def fetch_roads(territory):
    tags = {
        "highway": ["construction","crossing","living_street","motorway","motorway_link","motorway_junction","pedestrian","primary","primary_link","raceway","residential","road","secondary","secondary_link","services","tertiary","tertiary_link","track","trunk","trunk_link","turning_circle","turning_loop","unclassified",],
        "service": ["living_street", "emergency_access"]
    }

    if type(territory) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        territory = territory.unary_union

    try:
        roads = ox.features_from_polygon(territory, tags)
    except:
        print('too many roads...')
        roads = fetch_long_query(territory,tags)

    roads = roads.loc[roads.geom_type.isin(['LineString','MultiLineString'])]
    roads = roads.reset_index(drop=True)["geometry"]

    roads = gpd.GeoDataFrame(roads)

    return roads


def fetch_water(territory):

    if type(territory) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        territory = territory.unary_union

    water = ox.features_from_polygon(
        territory, {'riverbank':True,
                    'reservoir':True,
                    'basin':True,
                    'dock':True,
                    'canal':True,
                    'pond':True,
                    'natural':['water','bay'],
                    'waterway':['river','canal','ditch'],
                    'landuse':'basin'})
    water = water.loc[water.geom_type.isin(
        ['Polygon','MultiPolygon','LineString','MultiLineString'])]

    water = water.reset_index(drop=True)["geometry"].drop_duplicates()
    water = gpd.GeoDataFrame(water)

    return water


def fetch_railways(territory):

    if type(territory) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        territory = territory.unary_union

    railway = ox.features_from_polygon(
        territory, {"railway": "rail"}).reset_index(drop=True)

    try:
        railway = railway.query('service not in ["crossover","siding","yard"]')
    except:
        pass

    railway = railway["geometry"]
    railway  = gpd.GeoDataFrame(railway)

    return railway


def create_grid(gdf=None, n_cells=5, crs=4326):

    if type(gdf) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        xmin, ymin, xmax, ymax= gdf.total_bounds
    elif type(gdf) in [Polygon,MultiPolygon]:
        xmin, ymin, xmax, ymax= gdf.bounds

    cell_size = (xmax-xmin)/n_cells
    grid_cells = []

    for x0 in np.arange(xmin, xmax+cell_size, cell_size ):
        for y0 in np.arange(ymin, ymax+cell_size, cell_size):
            x1 = x0-cell_size
            y1 = y0+cell_size
            poly = shapely.geometry.box(x0, y0, x1, y1)
            grid_cells.append(poly)

    cells = gpd.GeoDataFrame(grid_cells, columns=['geometry'],crs=crs)

    if type(gdf) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        cells = gdf.overlay(cells,keep_geom_type=True)
    elif type(gdf) in [Polygon,MultiPolygon]:
        cells = gdf.intersection(cells)

    cells = cells[~cells.is_empty].set_crs(crs)
    cells = cells[np.logical_or(
        cells.type=='Polygon',cells.type=='MultiPolygon')]

    return cells



def fetch_long_query(territory, tags, subdivision=3,verbose=True):

    if type(territory) in [gpd.GeoDataFrame,gpd.GeoSeries]:
        territory = territory.unary_union

    cells = create_grid(territory,n_cells=subdivision)
    res_list = []

    for poly in tqdm(cells['geometry'],leave=False,disable=not verbose):
        try:
            objects_in_cell = ox.features_from_polygon(poly, tags)
        except InsufficientResponseError:
            continue
        except:
            objects_in_cell = fetch_long_query(poly,tags,subdivision)

        if len(objects_in_cell) > 0: res_list.append(objects_in_cell)

    res = pd.concat(res_list) if res_list else gpd.GeoDataFrame()

    return res