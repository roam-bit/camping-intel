/**
 * P2-4-E: 列表底部的"来源线索"卡片（unmapped_candidates 元素）。
 *
 * 没拿到精确坐标但 AI 找到了相关网页的候选，给用户能点开看的入口。
 */
import { Text, View } from '@tarojs/components'
import type { AISearchResponse } from '../types'
import { cleanInternalText, factSources, formatDate, openExternalUrl, sourceUrl } from '../utils/place-helpers'
import { AiGeneratedTag } from './AiContentLabels'

export type SourceLead = NonNullable<AISearchResponse['unmapped_candidates']>[number]

export function SourceLeadCard({ item }: { item: SourceLead }) {
  const sources = factSources(item.sources)
  return (
    <View className='unmapped-card'>
      <Text className='lead-name'>{item.name}</Text>
      <View className='ai-gen-chip-row'>
        <AiGeneratedTag />
      </View>
      <Text className='muted-text'>{cleanInternalText(item.reason)}</Text>
      <Text className='muted-text'>来源日期：{formatDate(item.latest_source_date)}</Text>
      {!!sources.length && (
        <View className='unmapped-sources'>
          {sources.slice(0, 3).map((source, index) => (
            <Text
              key={sourceUrl(source) || index}
              className='unmapped-source'
              onClick={() => openExternalUrl(sourceUrl(source))}
            >
              {source.domain || `来源${index + 1}`}
            </Text>
          ))}
        </View>
      )}
    </View>
  )
}
