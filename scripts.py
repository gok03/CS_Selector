#!/usr/bin/env python
# coding: utf-8

# # CityScope For World Scripts

cellsize = 20 #ref 20m = 1 block
max_blocks_x = 20
max_blocks_y = 20
buffer = 0.2
import geopandas as gpd
import geopy
from geopy.distance import geodesic
from shapely.geometry import Polygon
import numpy as np
import json
from pyproj import CRS, Transformer
from pyproj.transformer import Transformer, AreaOfInterest
import math
from osmxtract import overpass
from staticmap import StaticMap, CircleMarker
import urllib.request
import requests
from PIL import Image
from math import pi, log, tan, exp, atan, log2, floor
from pymongo import MongoClient, DESCENDING
import shapely
from bson.json_util import dumps



## codes for g3json
def get_geojson(bounds):
    query = overpass.ql_query(bounds, tag='building')
    response = overpass.request(query)
    return(response)

def inversebound(bound): return([bound[1],bound[0],bound[3],bound[2]])

def transfrom_latlng_to_m(lat,lng, bounds, h,w):
    center = ((bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2)
    x = geodesic(center, (bounds[0],center[1])).m
    y = geodesic(center, (center[0],bounds[1])).m
    crs = CRS.from_proj4("+proj=laea +lat_0="+str(center[0])+" +lon_0="+str(center[1])+" +x_0=0 +y_0=0 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs")
    transformer = Transformer.from_crs("epsg:4326", crs)
    y1,x1 = transformer.transform(lat, lng)
    return([(h/2)/y*y1,(w/2)/x*x1])
    #return(y1,x1)

def g_inverse(gdf):
    gdf.geometry = gdf.geometry.map(lambda polygon: shapely.ops.transform(lambda x, y: (y, x), polygon))
    return gdf

def find_one_grid_for_single_goem(geom):
    category_code = {"RL":0,"RM":1,"RS":2,"OL":3,"OM":4,"OS":5,"Amenities":7,"parking":9}
    category_value = {"RL":["apartments","bungalow","dormitory","hotel"],"RM":["detached","farm","house","residential"],"RS":["cabin","houseboat","static_caravan","terrace"],"OL":["commercial","industrial","office"],"OM":["retail","warehouse"],"OS":["kiosk","supermarket"],"Amenities":["bakehouse","civic","government","hospital","kindergarten","public","school","toilets","train_station","transportation","university"],"parking":["carport","garage","garages","parking"]}
    height = False
    if "height" in geom["properties"]:
        height = True 
    elif "building:height" in geom["properties"]:
        height = True
        geom["properties"]["height"] = geom["properties"]["building:height"]
    
    final_cat = "RM"
    final_height = 1
    
    for cat,val in category_value.items():
        if geom["properties"]["building"] in val:
            final_cat = cat
            
    if(height):
        if(geom["properties"]["height"] == geom["properties"]["height"]):
            if(geom["properties"]["height"][-1] == 'm'):
                geom["properties"]["height"] = geom["properties"]["height"][:-1]
            final_height = float(geom["properties"]["height"])

    if(final_height > 10):
        final_height = final_height/10
    elif(final_height <= 10):
        final_height = 1

    return(final_height,final_cat)

def get_q3jsjson(jsondata,h,w,bounds):
    json1 = {
      "block": 0,
      "layer": 0,
      "type": "block"
    }
    geojson = {"type":"FeatureCollection"}
    features = []
    features_without_bounds = []
    for i in jsondata["features"]:
        not_overflow = True
        if(i["geometry"]["type"] == "Polygon"):
            feature = {"ids":i["id"],"tags":i["properties"],"mtl":{"face":0}}
            centroid = transfrom_latlng_to_m(Polygon(i["geometry"]["coordinates"][0]).centroid.y,Polygon(i["geometry"]["coordinates"][0]).centroid.x,bounds, h,w)
            polygons = []
            for j in i["geometry"]["coordinates"]:
                sub_poly = []
                for k in j:
                    changed_lat_lng = transfrom_latlng_to_m(k[1],k[0], bounds, h,w)  
                    sub_poly.append(changed_lat_lng)
                polygons.append(sub_poly)
            temp_geom ={"coordinates":polygons,"type":"Polygon"}
            features_without_bounds.append({"geometry":temp_geom,"id":i["id"],"properties":i["properties"],"type": "Feature"})
            type_length = find_one_grid_for_single_goem(i)
            geom = {"centroids": [[centroid[0],centroid[1],0.0]],"h":type_length[0],"cat":type_length[1],"polygons":[polygons]}
            feature["geom"] = geom
            if(not_overflow):
                features.append(feature)
    json1["features"] = features
    geojson["features"] = features_without_bounds
    return(json1,geojson)

## codes for cityscope json & q3js block layer

def round_10(n):
    return(int(n + 9) // 10 * 10)

def round_near_x(n,x):
    return(int(n + 9) // x * x)

def find_distance_edge(bounds_map):
    coords_1 = (bounds_map[0], bounds_map[1])
    coords_2 = (bounds_map[0], bounds_map[3])
    coords_3 = (bounds_map[2], bounds_map[1])
    xlen = round_near_x(geopy.distance.distance(coords_1, coords_3).m,max_blocks_x)
    ylen = round_near_x(geopy.distance.distance(coords_1, coords_2).m,max_blocks_y)
    x_count = int(xlen/max_blocks_x)
    y_count = int(ylen/max_blocks_y)
    return (xlen,ylen,x_count,y_count)

def latlng_for_distance(lat,lng,distance,side):
    origin = geopy.Point(lat, lng)
    if(side == 'y'):
        destination = geodesic(kilometers=distance).destination(origin, 90)
    elif(side == 'x'):
        destination = geodesic(kilometers=distance).destination(origin, 0)
    return(round(destination.latitude,7), round(destination.longitude,7))

def matrix_latlng(ilat,ilng,x_distance,y_distance,x_count,y_count):
    latlng_height = [(ilat,ilng)]
    latlng_lenght = [(ilat,ilng)]
    for i in range(y_count,y_distance+y_count,y_count):
        latlng_height.append(latlng_for_distance(ilat,ilng,i/1000,"y"))
    for i in range(x_count,x_distance+x_count,x_count):
        latlng_lenght.append(latlng_for_distance(ilat,ilng,i/1000,"x"))
    return([latlng_lenght,latlng_height],[x_count,y_count])

def find_points(data):
    distances = find_distance_edge(data.total_bounds) # Finds the distance in meters in x,y
    print(data.total_bounds[0],data.total_bounds[1],distances[0],distances[1],distances[2],distances[3])
    return(matrix_latlng(data.total_bounds[0],data.total_bounds[1],distances[0],distances[1],distances[2],distances[3]))

def find_matrix_points(gdf,h,w):
    points_distance = find_points(gdf)
    points = points_distance[0]
    block_points = []
    for i in points:
        temp_points = []
        for j in i:
            temp = transfrom_latlng_to_m(j[0],j[1],gdf.total_bounds,h,w)
            temp_points.append([temp[0],temp[1]])
        block_points.append(temp_points)
    return(block_points,points_distance[1])

def reduce_by_05(bounds):
    #buffer = 0.01
    buffer = 0.05
    a1 = [bounds[0][0][0][0]+buffer,bounds[0][0][0][1]+buffer]
    a2 = [bounds[0][0][1][0]-buffer,bounds[0][0][1][1]+buffer]
    a3 = [bounds[0][0][2][0]-buffer,bounds[0][0][2][1]-buffer]
    a4 = [bounds[0][0][3][0]+buffer,bounds[0][0][3][1]-buffer]
    return([[[a1,a2,a3,a4]]])

def find_interaction(all_gpd,segment_bounds):
    bound = gpd.GeoSeries([Polygon(segment_bounds)])
    bound_gdframe = gpd.GeoDataFrame({'geometry': bound})
    return(gpd.overlay(all_gpd, bound_gdframe, how='intersection'))

def find_one_grid(igdf):
    if(len(igdf.geometry) > 0):
        count_yes = 0
        count_category = {"RL":0,"RM":0,"RS":0,"OL":0,"OM":0,"OS":0,"Amenities":0,"parking":0}
        category_code = {"RL":0,"RM":1,"RS":2,"OL":3,"OM":4,"OS":5,"Amenities":7,"parking":9}
        category_value = {"RL":["apartments","bungalow","dormitory","hotel"],"RM":["detached","farm","house","residential"],"RS":["cabin","houseboat","static_caravan","terrace"],"OL":["commercial","industrial","office"],"OM":["retail","warehouse"],"OS":["kiosk","supermarket"],"Amenities":["bakehouse","civic","government","hospital","kindergarten","public","school","toilets","train_station","transportation","university"],"parking":["carport","garage","garages","parking"]}
        height = False
        height_count = 0
        if "height" in igdf:
            height = True
        elif "building:height" in igdf:
            igdf.columns=igdf.columns.str.replace('building:height','height')
            height = True

        for i in range(0,len(igdf.building)):
            for cat,val in category_value.items():
                if igdf.building[i] in val:
                    count_category[cat] += 1
                elif(igdf.building[i] == "yes"):
                    count_yes = 1
            if(height):
                if(igdf.height[i] == igdf.height[i]):
                    if(igdf.height[i][-1] == 'm'):
                        igdf.height[i] = igdf.height[i][:-1]
                    height_count += int(float(igdf.height[i]))

        final_cat = max(count_category, key=count_category.get)
        if(count_category[final_cat] == 0):
            final_cat = "RM"

        final_height = 1
        if(height_count > 10):
            final_height = int(height_count/10)
            
        return([category_code[final_cat],final_height,0])
    else:
        return([-1,0,0])

def find_block_json(gdf,new_grid,h,w):
    matrix_distance = find_matrix_points(gdf,h,w)
    matrix = matrix_distance[0]
    ylen = len(matrix[0])-1
    xlen = len(matrix[1])-1
    #ylen = 10
    #xlen = 10
    json1 = {
      "block": 0,
      "layer": 1,
      "type": "block"
    }
    features = []
    dict_type = {0:"RL",1:"RM",2:"RS",3:"OL",4:"OM",5:"OS",7:"Amenities",9:"parking",-1:"road"}
    grid_for_cs = []
    for y in range(ylen):
        for x in range(0,xlen):
            feature = {"ids":str(y)+"-"+str(x),"tags":{},"mtl":{"face":0}}
            #print(y,x)
            p1 = [matrix[1][x][0],matrix[0][y][1]]
            p2 = [matrix[1][x+1][0],matrix[0][y][1]]
            p3 = [matrix[1][x+1][0],matrix[0][y+1][1]]
            p4 = [matrix[1][x][0],matrix[0][y+1][1]]
            bounds = reduce_by_05([[[p1,p2,p3,p4,p1]]])
            
            pbounds = [p1,p2,p3,p4,p1]
            
            centroid = [(p1[0]+p3[0])/2,(p1[1]+p3[1])/2]
            current_matrix = find_interaction(new_grid,pbounds)
            grid_value = find_one_grid(current_matrix)
            grid_for_cs.append(grid_value)
            #geom = {"centroids": [[centroid[0],centroid[1],0.0]],"h":grid[y][x][1] ,"cat": dict_type[grid[y][x][0]],"polygons":bounds}
            #print(str(x)+","+str(y)+":"+str(len(current_matrix.geometry))+"//"+str(grid_value))
            geom = {"centroids": [[centroid[0],centroid[1],0.0]],"h":grid_value[1] ,"cat": dict_type[grid_value[0]],"polygons":bounds}
            feature["geom"] = geom
            features.append(feature)
    json1["features"] = features
    return(json1,grid_for_cs,xlen,ylen,matrix_distance[1][0],matrix_distance[1][1])

def get_cityscope_json(geojson,grid,name,email,x,y,x_count,y_count):
    owner = {
      "name": email,
      "title": "-",
      "institute": "-"
    }
    mapping = {
      "type": {
        "-1": "MASK_INTERACTIVE",
        "0": "RL",
        "1": "RM",
        "2": "RS",
        "3": "OL",
        "4": "OM",
        "5": "OS",
        "7": "Amenities",
        "9": "parking"
      }
    }
    block = [
      "type",
      "height",
      "rotation"
    ]
    spatial = {
      "x_block_size": x_count,
      "Y_block_size": y_count,
      "x_length": x_count*x,
      "y_length": y_count*y,
      "physical_longitude": geojson.geometry[0].centroid.y,
      "cellsize": cellsize,
      "longitude": geojson.geometry[0].centroid.y,
      "rotation": 0,
      "nrows": x,
      "latitude": geojson.geometry[0].centroid.x,
      "ncols": y,
      "physical_latitude": geojson.geometry[0].centroid.x
    }
    final_api_data= {"grid":grid,"id":"","objects":{}, "header": {"spatial":spatial,"name":name,"block":block,"mapping":mapping,"owner":owner}}
    return final_api_data

def run_all(bounds,h,w,name,email):
    osm_json = get_geojson(bounds)
    geojson = overpass.as_geojson(osm_json, 'polygon') #geojson
    gdf = g_inverse(gpd.GeoDataFrame.from_features(geojson))
    bound = inversebound(gpd.GeoDataFrame.from_features(geojson).total_bounds)
    q3json = get_q3jsjson(geojson,h,w,bound)
    new_gdf = gpd.GeoDataFrame.from_features(q3json[1])
    find = find_block_json(gdf,new_gdf,h,w)
    cityscope_json = get_cityscope_json(gdf,find[1],name,email,find[2],find[3],find[4],find[5])
    return(cityscope_json)