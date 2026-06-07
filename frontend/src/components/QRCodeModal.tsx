/**
 * spec-017 / B 方案：链接二维码 modal
 *
 * 微信小程序不能直接调系统浏览器（平台限制）。变通方案：
 * - 把目标 URL 编成二维码、用户长按 → 微信识别 → 弹「在浏览器中打开」→ 跳系统浏览器
 *
 * 同时保留剪贴板复制兜底（用户实在不长按也能粘贴）。
 */
import { Image, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useState } from 'react'

import './QRCodeModal.css'

interface Props {
  url: string | null
  onClose: () => void
}

// spec-017 B 方案 v4：用 https 公网 URL 作 image src 直拉 PNG（cloudflared tunnel 提供 https）。
// 之前 v3 base64 dataURL 实测微信不识别为二维码；https 网络 PNG 是微信识别二维码的「黄金路径」。
// 前提：cloudflared tunnel 已起、TARO_APP_API_BASE 配为 https://xxx.trycloudflare.com
const API_BASE = process.env.TARO_APP_API_BASE || ''

export function QRCodeModal({ url, onClose }: Props) {
  const [qrImageUrl, setQrImageUrl] = useState<string>('')
  const [genError, setGenError] = useState<string>('')

  useEffect(() => {
    if (!url) {
      setQrImageUrl('')
      setGenError('')
      return
    }
    if (!API_BASE) {
      setGenError('后端地址未配置、无法生成二维码')
      return
    }
    // 直接喂 image src：https 公网 PNG 网络图。微信对这种格式才会弹「识别图中二维码」菜单。
    setQrImageUrl(`${API_BASE}/api/v1/qrcode?url=${encodeURIComponent(url)}&size=480`)
    setGenError('')
  }, [url])

  if (!url) return null

  // 截短显示用 URL（完整 url 编进二维码、UI 只展示前缀让用户对照）
  const displayUrl = url.length > 60 ? `${url.slice(0, 50)}…${url.slice(-8)}` : url

  const handleCopy = () => {
    if (!url) return
    Taro.setClipboardData({
      data: url,
      success: () => {
        Taro.showToast({
          title: '链接已复制，打开浏览器粘贴即可',
          icon: 'none',
          duration: 2500,
        })
      },
    })
  }

  return (
    <View className='qr-modal-mask' onClick={onClose}>
      <View className='qr-modal-card' onClick={(e) => e.stopPropagation()}>
        <Text className='qr-modal-title'>在浏览器中打开链接</Text>
        <Text className='qr-modal-subtitle'>推荐用下方「复制链接」按钮、最稳</Text>
        <View className='qr-modal-img-wrap'>
          {qrImageUrl ? (
            <Image className='qr-modal-img' src={qrImageUrl} mode='aspectFit' showMenuByLongpress />
          ) : (
            <Text className='qr-modal-loading'>{genError || '生成二维码中…'}</Text>
          )}
        </View>
        <Text className='qr-modal-qr-hint'>或长按二维码选「识别」（真机不一定支持）</Text>
        <Text className='qr-modal-url'>{displayUrl}</Text>
        <View className='qr-modal-copy-btn' onClick={handleCopy}>
          <Text>📋 复制链接</Text>
        </View>
        <View className='qr-modal-close-btn' onClick={onClose}>
          <Text>关闭</Text>
        </View>
      </View>
    </View>
  )
}
