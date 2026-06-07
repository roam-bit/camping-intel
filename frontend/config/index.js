const fs = require('node:fs')
const path = require('node:path')

function readRootEnv() {
  const envPath = path.resolve(__dirname, '../../.env')
  if (!fs.existsSync(envPath)) return {}
  return fs
    .readFileSync(envPath, 'utf8')
    .split(/\r?\n/)
    .reduce((env, line) => {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) return env
      const match = trimmed.match(/^([^=]+)=(.*)$/)
      if (!match) return env
      const key = match[1].trim()
      const value = match[2].trim().replace(/^['"]|['"]$/g, '')
      env[key] = value
      return env
    }, {})
}

const rootEnv = readRootEnv()

function envValue(key, fallback = '') {
  return process.env[key] || rootEnv[key] || fallback
}

// 后端地址唯一来源（spec-011 US1）：本地开发兜底为 127.0.0.1；
// 生产由环境变量 / 根 .env 的 TARO_APP_API_BASE 覆盖。
const apiBase = envValue('TARO_APP_API_BASE', 'http://127.0.0.1:8000')

// spec-011 FR-003：小程序构建若仍指向 localhost，产物在微信端必然连不上后端
// （微信小程序禁止请求 localhost/IP）。构建期 warn 提示，不中断构建——
// 保留「开发者用微信工具连本机后端调试」的合理场景。
if (process.env.TARO_ENV === 'weapp' && /localhost|127\.0\.0\.1/.test(apiBase)) {
  console.warn(
    `\n⚠️  [spec-011] 小程序构建的 TARO_APP_API_BASE 仍是 ${apiBase}\n` +
      '   微信小程序禁止请求 localhost/IP，此产物在微信端将连不上后端。\n' +
      '   生产构建请设环境变量 TARO_APP_API_BASE 为已备案的 HTTPS 域名。\n'
  )
}

// H5 与小程序分开输出目录，避免互相覆盖（两端都用 dist 时后构建的会盖掉前者）
// 小程序 → dist/（project.config.json 的 miniprogramRoot 指向它）；H5 → dist-h5/
const outputRoot = process.env.TARO_ENV === 'h5' ? 'dist-h5' : 'dist'

const config = {
  projectName: 'camping-ai-taro',
  date: '2026-05-13',
  designWidth: 750,
  deviceRatio: {
    640: 2.34 / 2,
    750: 1,
    828: 1.81 / 2
  },
  sourceRoot: 'src',
  outputRoot,
  plugins: [],
  env: {
    DEBUG: JSON.stringify(''),
    TARO_APP_API_BASE: JSON.stringify(apiBase),
    TARO_APP_AMAP_WEB_KEY: JSON.stringify(envValue('TARO_APP_AMAP_WEB_KEY') || envValue('AMAP_WEB_KEY') || envValue('AMAP_JS_KEY')),
    TARO_APP_AMAP_SECURITY_CODE: JSON.stringify(
      envValue('TARO_APP_AMAP_SECURITY_CODE') || envValue('AMAP_SECURITY_CODE') || envValue('AMAP_JS_SECURITY_CODE')
    )
  },
  defineConstants: {},
  copy: {
    // marker.png 必须作为独立文件进包——weapp <map> 的 marker iconPath 不认 base64
    // 内联（webpack 默认会把小图内联成 data URI），故直接 copy 到产物 assets/（spec-012）
    patterns: [{ from: 'src/assets/', to: `${outputRoot}/assets/` }],
    options: {}
  },
  framework: 'react',
  compiler: 'webpack5',
  cache: {
    enable: false
  },
  mini: {
    postcss: {
      pxtransform: {
        enable: true,
        config: {}
      },
      cssModules: {
        enable: false,
        config: {
          namingPattern: 'module',
          generateScopedName: '[name]__[local]___[hash:base64:5]'
        }
      }
    }
  },
  h5: {
    publicPath: '/',
    staticDirectory: 'static',
    devServer: {
      host: '0.0.0.0',
      port: 10086
    },
    router: {
      mode: 'browser'
    },
    postcss: {
      autoprefixer: {
        enable: true,
        config: {}
      },
      cssModules: {
        enable: false,
        config: {
          namingPattern: 'module',
          generateScopedName: '[name]__[local]___[hash:base64:5]'
        }
      }
    }
  }
}

module.exports = function () {
  return config
}
