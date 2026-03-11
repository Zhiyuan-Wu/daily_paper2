import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:18000';
const extraAllowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean);
const allowedHosts = ['4cb9781588el.vicp.fun', ...extraAllowedHosts];

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
});
