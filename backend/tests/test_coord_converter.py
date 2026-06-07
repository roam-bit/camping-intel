"""坐标转换单元测试"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.coord_converter import (
    bd09_to_wgs84,
    gcj02_to_wgs84,
    wgs84_to_gcj02,
    bd09_to_gcj02,
)


def test_gcj02_to_wgs84():
    """测试 GCJ-02 转 WGS84"""
    # 天安门坐标
    lon_gcj, lat_gcj = 116.397827, 39.909678
    lon_wgs, lat_wgs = gcj02_to_wgs84(lon_gcj, lat_gcj)
    # WGS84 天安门约为 116.397428, 39.90923
    assert abs(lon_wgs - 116.397) < 0.01
    assert abs(lat_wgs - 39.909) < 0.01


def test_bd09_to_wgs84():
    """测试 BD09 转 WGS84"""
    # 百度地图天安门坐标
    lon_bd, lat_bd = 116.403874, 39.914888
    lon_wgs, lat_wgs = bd09_to_wgs84(lon_bd, lat_bd)
    assert abs(lon_wgs - 116.397) < 0.01
    assert abs(lat_wgs - 39.909) < 0.01


def test_roundtrip_wgs84():
    """测试 WGS84 -> GCJ02 -> WGS84 往返"""
    lon, lat = 116.397428, 39.90923
    lon_gcj, lat_gcj = wgs84_to_gcj02(lon, lat)
    lon_back, lat_back = gcj02_to_wgs84(lon_gcj, lat_gcj)
    assert abs(lon_back - lon) < 0.0001
    assert abs(lat_back - lat) < 0.0001


def test_bd09_to_gcj02():
    """测试 BD09 转 GCJ-02"""
    lon_bd, lat_bd = 116.403874, 39.914888
    lon_gcj, lat_gcj = bd09_to_gcj02(lon_bd, lat_bd)
    assert abs(lon_gcj - 116.397) < 0.01
    assert abs(lat_gcj - 39.909) < 0.01


def test_out_of_china():
    """测试境外坐标不转换"""
    lon, lat = gcj02_to_wgs84(-100.0, 40.0)
    assert lon == -100.0
    assert lat == 40.0
