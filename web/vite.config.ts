import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  // 개발할 때(npm run dev)만: API 는 uv run bnb2 web 이 띄운 8000 번으로 보낸다
  build: { chunkSizeWarningLimit: 1500 }, // 로컬 전용 도구라 한 덩어리로 둔다
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
