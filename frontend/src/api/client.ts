import axios from 'axios'

// VITE_API_URL est definie dans .env.development (local) et .env.production (Render).
const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const apiClient = axios.create({ baseURL })
