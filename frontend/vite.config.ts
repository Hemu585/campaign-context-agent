import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The UI origin must stay exactly http://127.0.0.1:5173: the API's CORS
// allowlist and Origin check depend on it (API_CONTRACTS, LOCAL_SETUP section 6).
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true },
})
