import Taro from '@tarojs/taro'
import type { Place } from '../types'
import { wgs84ToGcj02 } from './coords'

declare global {
  interface Window {
    AMap?: any
    _AMapSecurityConfig?: { securityJsCode?: string }
  }
}

const AMAP_KEY = process.env.TARO_APP_AMAP_WEB_KEY || ''
const AMAP_SECURITY_CODE = process.env.TARO_APP_AMAP_SECURITY_CODE || ''

let loadingPromise: Promise<any> | null = null

export function hasAmapKey() {
  return Boolean(AMAP_KEY)
}

export function loadAmap() {
  if (typeof window === 'undefined') return Promise.reject(new Error('高德地图只在 H5 浏览器环境初始化'))
  if (window.AMap) return Promise.resolve(window.AMap)
  if (!AMAP_KEY) return Promise.reject(new Error('缺少 TARO_APP_AMAP_WEB_KEY，无法加载高德地图'))
  if (AMAP_SECURITY_CODE) {
    window._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_CODE }
  }
  if (!loadingPromise) {
    loadingPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_KEY}&plugin=AMap.Scale,AMap.ToolBar,AMap.MarkerCluster`
      script.async = true
      script.onload = () => resolve(window.AMap)
      script.onerror = () => reject(new Error('高德地图 JS API 加载失败'))
      document.head.appendChild(script)
    })
  }
  return loadingPromise
}

export function toAmapPosition(place: Pick<Place, 'longitude' | 'latitude'>): [number, number] {
  return wgs84ToGcj02(place.longitude, place.latitude)
}

export function openAmapNavigation(place: Place) {
  const [lon, lat] = toAmapPosition(place)
  // 小程序端无 window，window.open 打不开高德网页导航 —— 改用 Taro.openLocation
  // 打开微信内置位置查看页，用户可在那里「到这里去」唤起系统地图导航（spec-012 US5）。
  if (process.env.TARO_ENV !== 'h5') {
    Taro.openLocation({ longitude: lon, latitude: lat, name: place.name, scale: 14 })
    return
  }
  const name = encodeURIComponent(place.name)
  const url = `https://uri.amap.com/navigation?to=${lon},${lat},${name}&mode=car&policy=1&src=camping-ai&coordinate=gaode`
  if (typeof window !== 'undefined') window.open(url, '_blank')
}
