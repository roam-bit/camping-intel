const PI = 3.1415926535897932384626
const A = 6378245.0
const EE = 0.00669342162296594323

function outOfChina(lon: number, lat: number) {
  return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function transformLat(lon: number, lat: number) {
  let ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * Math.sqrt(Math.abs(lon))
  ret += ((20.0 * Math.sin(6.0 * lon * PI) + 20.0 * Math.sin(2.0 * lon * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(lat * PI) + 40.0 * Math.sin((lat / 3.0) * PI)) * 2.0) / 3.0
  ret += ((160.0 * Math.sin((lat / 12.0) * PI) + 320 * Math.sin((lat * PI) / 30.0)) * 2.0) / 3.0
  return ret
}

function transformLon(lon: number, lat: number) {
  let ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * Math.sqrt(Math.abs(lon))
  ret += ((20.0 * Math.sin(6.0 * lon * PI) + 20.0 * Math.sin(2.0 * lon * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(lon * PI) + 40.0 * Math.sin((lon / 3.0) * PI)) * 2.0) / 3.0
  ret += ((150.0 * Math.sin((lon / 12.0) * PI) + 300.0 * Math.sin((lon / 30.0) * PI)) * 2.0) / 3.0
  return ret
}

export function wgs84ToGcj02(lon: number, lat: number): [number, number] {
  if (outOfChina(lon, lat)) return [lon, lat]
  let dlat = transformLat(lon - 105.0, lat - 35.0)
  let dlon = transformLon(lon - 105.0, lat - 35.0)
  const radlat = (lat / 180.0) * PI
  let magic = Math.sin(radlat)
  magic = 1 - EE * magic * magic
  const sqrtmagic = Math.sqrt(magic)
  dlat = (dlat * 180.0) / (((A * (1 - EE)) / (magic * sqrtmagic)) * PI)
  dlon = (dlon * 180.0) / ((A / sqrtmagic) * Math.cos(radlat) * PI)
  return [lon + dlon, lat + dlat]
}
