import {defineConfig} from 'vite';

export default defineConfig({
  build: {
    // The locked Rollup version spends excessive memory analysing nested React calls.
    // Import icons individually and keep esbuild minification, avoiding that extra pass.
    rollupOptions: {treeshake: false},
  },
});
