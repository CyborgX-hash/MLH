// Empty by default: requests go to the same origin and Vite proxies /api to the backend.
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''
