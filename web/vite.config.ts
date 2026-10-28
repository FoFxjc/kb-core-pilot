import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The build is committed (src/kb_core/serve/static) and served by `kb-core serve` at /ui/; every output name is a
// content hash so a rebuild of the same source gives the same files.
export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  build: {
    outDir: '../src/kb_core/serve/static',
    emptyOutDir: true,
    sourcemap: false,
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 2048,
    license: false,
    rolldownOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: { host: '127.0.0.1', proxy: { '/v1': 'http://127.0.0.1:8200' } },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], globals: false },
});
