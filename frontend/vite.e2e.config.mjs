import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  root: 'C:/Users/touhe/OneDrive/Desktop/proooctify/frontend',
  plugins: [react()],
  server: { port: 5174, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:8198', changeOrigin: true } } },
})