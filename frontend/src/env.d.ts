declare const process: {
  env: {
    TARO_ENV?: string
    TARO_APP_API_BASE: string
    TARO_APP_AMAP_WEB_KEY?: string
    TARO_APP_AMAP_SECURITY_CODE?: string
  }
}

declare function defineAppConfig(config: unknown): unknown
declare function definePageConfig(config: unknown): unknown
