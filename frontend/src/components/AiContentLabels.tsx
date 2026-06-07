/**
 * spec-015：AI 生成内容合规标识——合规文案的全站单一来源。
 * 改文案只改此处，避免 4 处组件各自硬编码导致漂移。
 */
import { Text, View } from '@tarojs/components'

/** 显式标识（《AI 生成合成内容标识办法》+ 强制性国标 GB 45438-2025）。复用 ai-gen-chip 视觉风格。 */
export function AiGeneratedTag() {
  return <Text className='ai-gen-chip'>AI 生成整理</Text>
}

/** 风险提示（《生成式 AI 服务管理暂行办法》）。集中呈现一次，由首页放在结果列表区。 */
export function AiRiskNotice() {
  return (
    <View className='ai-risk-notice'>
      <Text className='ai-risk-notice-text'>内容由 AI 整理，仅供参考，请出行前自行核实</Text>
    </View>
  )
}
