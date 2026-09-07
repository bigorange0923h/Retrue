import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  // 生产站点部署在 /retrue/；开发服务器仍保持根路径，避免影响本地调试。
  const base = command === 'build' ? (process.env.VITE_APP_BASE_PATH || '/retrue/') : '/'

  return {
    base,
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      // 开发环境代理到后端，保持 Cookie 同源，便于 Session 认证。
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
