"""BD09 / GCJ02 / WGS84 坐标转换工具

百度地图使用 BD09，高德/小红书使用 GCJ02，PostGIS 使用 WGS84。
"""

import math

x_pi = 3.14159265358979324 * 3000.0 / 180.0
pi = 3.1415926535897932384626
a = 6378245.0
ee = 0.00669342162296594323


def _transform_lat(lon: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * pi) + 20.0 * math.sin(2.0 * lon * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 * math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320.0 * math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(lon: float, lat: float) -> float:
    ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * pi) + 20.0 * math.sin(2.0 * lon * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lon * pi) + 40.0 * math.sin(lon / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lon / 12.0 * pi) + 300.0 * math.sin(lon / 30.0 * pi)) * 2.0 / 3.0
    return ret


def _out_of_china(lon: float, lat: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    """GCJ-02 (火星坐标系) 转 WGS84"""
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    mglat = lat + dlat
    mglon = lon + dlon
    return lon * 2 - mglon, lat * 2 - mglat


def wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 转 GCJ-02"""
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    return lon + dlon, lat + dlat


def bd09_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    """BD09 转 GCJ-02"""
    x = lon - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return z * math.cos(theta), z * math.sin(theta)


def gcj02_to_bd09(lon: float, lat: float) -> tuple[float, float]:
    """GCJ-02 转 BD09"""
    z = math.sqrt(lon * lon + lat * lat) + 0.00002 * math.sin(lat * x_pi)
    theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * x_pi)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    """BD09 转 WGS84"""
    lon, lat = bd09_to_gcj02(lon, lat)
    return gcj02_to_wgs84(lon, lat)


def wgs84_to_bd09(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 转 BD09"""
    lon, lat = wgs84_to_gcj02(lon, lat)
    return gcj02_to_bd09(lon, lat)
