import { defineConfig } from 'vite';

export default defineConfig({
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: 'office.html',
      output: {
        entryFileNames: 'office.js',
        assetFileNames: (asset) => asset.name?.endsWith('.css') ? 'office.css' : 'office/[name][extname]'
      }
    }
  }
});
