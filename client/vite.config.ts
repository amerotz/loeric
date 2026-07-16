import { sveltekit } from '@sveltejs/kit/vite'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit()
	],
	server: {
		port: 5173, // optional
		proxy: {
			'/api': {
				target: 'http://localhost:8080', // <-- your Python port
				changeOrigin: true
			},
			 '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
        changeOrigin: true,
      },
		}
	}
});
