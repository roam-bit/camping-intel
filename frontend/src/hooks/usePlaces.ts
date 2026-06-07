/**
 * P2-4-G: 周边点位列表 state + 加载函数。
 *
 * 把 places state + loadPlaces 函数 + loading state 封装。
 * onError 由父组件传入，方便统一收口 setWarning（保持 IndexPage 是唯一 warning 持有者）。
 *
 * spec 001-fix-source-geo-filter：loadPlaces 接受 q 参数 + 暴露 searchMetadata，
 * 让父组件能根据 geocoder/detected_place 决定空状态文案。
 */
import { useCallback, useState } from 'react'
import { getPlaces } from '../api/client'
import type { Place, PlacesSearchMetadata } from '../types'

export interface UsePlacesArgs {
  userCoord: { lat: number; lon: number }
  radiusKm: number
  onError?: (msg: string) => void
}

export function usePlaces({ userCoord, radiusKm, onError }: UsePlacesArgs) {
  const [places, setPlaces] = useState<Place[]>([])
  const [loading, setLoading] = useState(false)
  const [searchMetadata, setSearchMetadata] = useState<PlacesSearchMetadata | null>(null)

  const loadPlaces = useCallback(
    async (q?: string) => {
      setLoading(true)
      try {
        const data = await getPlaces({
          lat: userCoord.lat,
          lon: userCoord.lon,
          radius_km: radiusKm,
          category: '全部',
          min_credibility: 0,
          limit: 240,
          ...(q && q.trim() ? { q: q.trim() } : {}),
        })
        setPlaces(data.places || [])
        setSearchMetadata(data.search_metadata ?? null)
      } catch (error) {
        onError?.(error instanceof Error ? error.message : '点位加载失败')
      } finally {
        setLoading(false)
      }
    },
    [userCoord.lat, userCoord.lon, radiusKm, onError]
  )

  return { places, loading, loadPlaces, searchMetadata }
}
