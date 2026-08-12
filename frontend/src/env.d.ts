declare const process: {
  env: {
    TARO_ENV?: string
    TARO_APP_API_BASE: string
    TARO_APP_AMAP_WEB_KEY?: string
    TARO_APP_AMAP_SECURITY_CODE?: string
  }
}

// webpack 提供的 require（用于平台条件加载样式，如 index.tsx 按 TARO_ENV 引 index.h5.css）
declare function require(path: string): unknown

declare function defineAppConfig(config: unknown): unknown
declare function definePageConfig(config: unknown): unknown
