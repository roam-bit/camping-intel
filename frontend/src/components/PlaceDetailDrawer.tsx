/**
 * P2-4-E: 点位详情抽屉。
 *
 * 用户点列表卡或地图 marker 后弹出，展示:
 *  - 标题 / 来源标记 / AI 摘要
 *  - 富信源卡片列表（PlatformIcon + 标题 + 摘要片段 + 求证进度）
 *  - 8 格设施 info-cell（费用 / 过夜 / 厕所 / 水源 / 充电 / 车型 / 来源日期 / 来源数）
 *  - 风险备注 + 合规话术
 *  - 底部按钮：可停可过夜反馈 / 有风险反馈 / 马上导航（求证后高亮）
 */
import { Button, Text, View } from '@tarojs/components'
import type { Place, SourceItem } from '../types'
import { openAmapNavigation } from '../utils/amap'
import {
  cleanRiskTags,
  displaySummary,
  factSources,
  formatDate,
  formatDistance,
  isPersistedPlace,
  latestDateOf,
  openExternalUrl,
  sourceDate,
  sourceKindText,
  sourceTimeText,
  sourceUrl,
  statusText,
  vehicleText,
} from '../utils/place-helpers'
import { PlatformIcon } from './PlatformIcon'
import { AiGeneratedTag } from './AiContentLabels'

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <View className='info-cell'>
      <Text className='cell-label'>{label}</Text>
      <Text className='cell-value'>{value}</Text>
    </View>
  )
}

export interface PlaceDetailDrawerProps {
  place: Place
  viewedSources: Set<string>
  onClose: () => void
  /** 点击信源时回调（用于打点 viewedSources）；最终是否外跳由组件自己处理 */
  onSourceViewed: (url: string) => void
  /** 反馈按钮回调 */
  onQuickFeedback: (payload: Record<string, unknown>) => void
}

export function PlaceDetailDrawer({
  place,
  viewedSources,
  onClose,
  onSourceViewed,
  onQuickFeedback,
}: PlaceDetailDrawerProps) {
  const placeSources = factSources(place.sources)
  const totalSources = placeSources.length
  const viewedInPlace = placeSources.filter((src: SourceItem) => {
    const url = sourceUrl(src)
    return url && viewedSources.has(url)
  }).length
  const hasVerifiedAny = viewedInPlace > 0

  return (
    <View className='detail-mask' onClick={onClose}>
      <View className='detail-drawer' onClick={(event) => event.stopPropagation()}>
        <View className='drawer-header'>
          <View className='detail-heading'>
            <Text className='detail-name'>{place.name}</Text>
            <Text className='detail-meta'>
              {place.city || place.province} · {formatDistance(place.distance_km)} · {place.type}
            </Text>
          </View>
          <Button className='close-btn' onClick={onClose}>×</Button>
        </View>
        <View className='detail-body'>
          <View className='detail-summary-row'>
            <View className='detail-status-row'>
              <Text className='layer-badge source'>{sourceKindText(place)}</Text>
              <Text className='layer-badge neutral'>{sourceTimeText(place)}</Text>
            </View>
          </View>
          <View className='ai-gen-chip-row'>
            <AiGeneratedTag />
            <Text className='ai-gen-hint'>结合下方信源自行核验</Text>
          </View>
          <Text className='summary'>{displaySummary(place)}</Text>

          <View className='sources-section'>
            <View className='sources-header'>
              <Text className='section-title'>信息来源 {totalSources}</Text>
              {totalSources > 0 && (
                <Text className={`verify-progress ${hasVerifiedAny ? 'has-progress' : ''}`}>
                  {hasVerifiedAny ? `已查看 ${viewedInPlace}/${totalSources}` : '点开下面的信源链接来求证'}
                </Text>
              )}
            </View>
            {placeSources.map((source, index) => {
              const url = sourceUrl(source)
              const viewed = !!url && viewedSources.has(url)
              return (
                <View
                  key={source.id || url || index}
                  className={`source-card-rich ${viewed ? 'viewed' : ''}`}
                  onClick={() => {
                    if (url) {
                      onSourceViewed(url)
                      openExternalUrl(url)
                    }
                  }}
                >
                  <PlatformIcon domain={source.domain} />
                  <View className='source-card-main'>
                    <View className='source-card-top'>
                      <Text className='source-title-rich'>{source.title || source.domain || '公开来源'}</Text>
                      {viewed && <Text className='source-viewed-badge'>已读</Text>}
                    </View>
                    {!!source.snippet && (
                      <Text className='source-snippet-rich'>
                        {(source.snippet || '').slice(0, 80)}
                        {(source.snippet || '').length > 80 ? '…' : ''}
                      </Text>
                    )}
                    <View className='source-card-foot'>
                      <Text className='source-meta-rich'>{source.domain || ''} · {formatDate(sourceDate(source))}</Text>
                      <Text className='source-view-btn'>查看原文 ↗</Text>
                    </View>
                  </View>
                </View>
              )
            })}
            {!totalSources && <Text className='source-empty'>暂无公开网页信源。</Text>}
          </View>

          <View className='facility-grid'>
            <InfoCell label='费用' value={statusText(place.price_clues?.join('、'))} />
            <InfoCell label='过夜/露营' value={statusText(place.overnight_clues?.join('、'))} />
            <InfoCell label='厕所' value={statusText(place.toilet_status)} />
            <InfoCell label='水源' value={statusText(place.water_status)} />
            <InfoCell label='充电' value={statusText(place.electricity_status)} />
            <InfoCell label='车型' value={vehicleText(place)} />
            <InfoCell label='来源日期' value={formatDate(latestDateOf(place))} />
            <InfoCell label='来源数量' value={`${totalSources} 条`} />
          </View>
          {!!cleanRiskTags(place.risk_tags).length && (
            <Text className='risk'>来源备注：{cleanRiskTags(place.risk_tags).join('、')}</Text>
          )}
          <Text className='disclaimer'>
            AI 生成内容，仅供出行参考；具体可行性需以现场和官方信息为准。实际停车、露营、过夜需遵守当地法律法规及现场管理要求。
          </Text>
        </View>
        <View className='drawer-actions'>
          {isPersistedPlace(place) && (
            <Button
              className='secondary-btn'
              onClick={() => onQuickFeedback({ can_park_now: '是', can_overnight: '是' })}
            >
              可停/可过夜
            </Button>
          )}
          {isPersistedPlace(place) && (
            <Button
              className='secondary-btn danger'
              onClick={() => onQuickFeedback({ was_warned: true, comment: '用户反馈存在现场风险' })}
            >
              有风险
            </Button>
          )}
          <Button
            className={`primary-btn nav-main-btn ${hasVerifiedAny ? 'verified' : ''}`}
            onClick={() => openAmapNavigation(place)}
          >
            {hasVerifiedAny ? '已求证 ✓ 马上导航' : '马上导航'}
          </Button>
        </View>
      </View>
    </View>
  )
}
