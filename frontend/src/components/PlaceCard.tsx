/**
 * P2-4-E: 列表卡片（compact 紧凑模式 + 完整模式）。
 *
 * 展示 place name / 类别 / 距离 / 设施 badge / 摘要 / 信源元信息 + 导航按钮。
 *
 * 双端形态（2026-06-12 起）：
 * - H5：demo2_v1b 设计稿样式——类型徽章右上、设施=emoji 圆点（只显示具备的）、
 *   "✓ N 条信源"绿色强调、不渲染「源」缩略块
 * - weapp：保持原版式（文字设施徽章 + 缩略块）。TARO_ENV 是编译期常量，
 *   各端产物只含自己分支的代码
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

/** H5：只显示"具备"的设施，emoji 圆点形态（demo2 样式） */
function FacilityDots({ place }: { place: Place }) {
  const dots = [
    { emoji: '🚻', ok: hasFacilitySignal(place.toilet_status) },
    { emoji: '💧', ok: hasFacilitySignal(place.water_status) },
    { emoji: '⚡', ok: hasFacilitySignal(place.electricity_status) },
  ].filter((d) => d.ok)
  if (!dots.length) return null
  return (
    <View className='facility-dots'>
      {dots.map((d) => (
        <Text key={d.emoji} className='facility-dot'>{d.emoji}</Text>
      ))}
    </View>
  )
}

/** place.type → 主题色徽章的样式后缀 */
function typeClass(type?: string | null) {
  if (type === '驻车点') return 'park'
  if (type === '野外露营') return 'wild'
  return 'camp'
}

export interface PlaceCardProps {
  place: Place
  onClick: () => void
  compact?: boolean
}

export function PlaceCard({ place, onClick, compact = false }: PlaceCardProps) {
  return (
    <View className={`place-card ${compact ? 'compact' : ''}`} onClick={onClick}>
      {process.env.TARO_ENV !== 'h5' && (
        <View className='place-thumb'>
          <Text className='thumb-mark'>源</Text>
        </View>
      )}
      <View className='place-card-main'>
        <View className='card-top'>
          <View className='card-title-group'>
            <Text className='place-name'>{place.name}</Text>
            <Text className='place-meta'>
              {process.env.TARO_ENV === 'h5'
                ? `${sourceKindText(place)} · ${formatDistance(place.distance_km)}`
                : `${sourceKindText(place)} · ${place.type} · ${formatDistance(place.distance_km)}`}
            </Text>
          </View>
          {process.env.TARO_ENV === 'h5' && <Text className={`type-badge ${typeClass(place.type)}`}>{place.type}</Text>}
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
        {process.env.TARO_ENV !== 'h5' && (
          <View className='facility-badges'>
            <FacilityBadge label='卫' text='厕所' active={hasFacilitySignal(place.toilet_status)} />
            <FacilityBadge label='水' text='水源' active={hasFacilitySignal(place.water_status)} />
            <FacilityBadge label='电' text='接电' active={hasFacilitySignal(place.electricity_status)} />
          </View>
        )}
        <Text className='place-summary'>{displaySummary(place)}</Text>
        <View className='ai-gen-chip-row'>
          <AiGeneratedTag />
        </View>
        <View className='card-tags'>
          <Text className='card-tag-sources'>{process.env.TARO_ENV === 'h5' ? `✓ ${displaySourceCount(place)} 条信源` : `信源 ${displaySourceCount(place)}`}</Text>
          <Text>{sourceTimeText(place)}</Text>
          <Text>{formatDate(latestDateOf(place))}</Text>
          {process.env.TARO_ENV === 'h5' && <FacilityDots place={place} />}
        </View>
      </View>
    </View>
  )
}
