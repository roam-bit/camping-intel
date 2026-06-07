/**
 * P2-4-E: 列表卡片（compact 紧凑模式 + 完整模式）。
 *
 * 展示 place name / 类别 / 距离 / 设施 badge / 摘要 / 信源元信息 + 导航按钮。
 */
import { Button, Text, View } from '@tarojs/components'
import type { Place } from '../types'
import { openAmapNavigation } from '../utils/amap'
import { AiGeneratedTag } from './AiContentLabels'
import {
  displaySourceCount,
  displaySummary,
  formatDate,
  formatDistance,
  hasFacilitySignal,
  latestDateOf,
  sourceKindText,
  sourceTimeText,
} from '../utils/place-helpers'

function FacilityBadge({ label, text, active }: { label: string; text: string; active: boolean }) {
  return (
    <View className={`facility-badge ${active ? 'active' : 'inactive'}`}>
      <Text className='facility-icon'>{label}</Text>
      <Text>{text}</Text>
    </View>
  )
}

export interface PlaceCardProps {
  place: Place
  onClick: () => void
  compact?: boolean
}

export function PlaceCard({ place, onClick, compact = false }: PlaceCardProps) {
  return (
    <View className={`place-card ${compact ? 'compact' : ''}`} onClick={onClick}>
      <View className='place-thumb'>
        <Text className='thumb-mark'>源</Text>
      </View>
      <View className='place-card-main'>
        <View className='card-top'>
          <View className='card-title-group'>
            <Text className='place-name'>{place.name}</Text>
            <Text className='place-meta'>{sourceKindText(place)} · {place.type} · {formatDistance(place.distance_km)}</Text>
          </View>
          <Button
            className='card-nav-btn'
            onClick={(event) => {
              event.stopPropagation()
              openAmapNavigation(place)
            }}
          >
            导航
          </Button>
        </View>
        <View className='facility-badges'>
          <FacilityBadge label='卫' text='厕所' active={hasFacilitySignal(place.toilet_status)} />
          <FacilityBadge label='水' text='水源' active={hasFacilitySignal(place.water_status)} />
          <FacilityBadge label='电' text='接电' active={hasFacilitySignal(place.electricity_status)} />
        </View>
        <Text className='place-summary'>{displaySummary(place)}</Text>
        <View className='ai-gen-chip-row'>
          <AiGeneratedTag />
        </View>
        <View className='card-tags'>
          <Text>信源 {displaySourceCount(place)}</Text>
          <Text>{sourceTimeText(place)}</Text>
          <Text>{formatDate(latestDateOf(place))}</Text>
        </View>
      </View>
    </View>
  )
}
