/**
 * P2-4-B: 平台 icon（小红书 / B 站 / 抖音 / 马蜂窝 / 知乎 / 微博 / 政府 / 通用）。
 * 从域名推断平台 → 显示品牌色背景 + 中文字符（不依赖 favicon 外网）。
 */
import { Text, View } from '@tarojs/components'
import { detectPlatform, PLATFORM_META } from '../utils/place-helpers'

export function PlatformIcon({ domain }: { domain?: string | null }) {
  const key = detectPlatform(domain)
  const meta = PLATFORM_META[key]
  return (
    <View className='platform-icon' style={{ background: meta.bg }}>
      <Text className='platform-icon-char'>{meta.char}</Text>
    </View>
  )
}
