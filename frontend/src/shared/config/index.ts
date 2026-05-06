export const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/$/, '')

export const appConfig = {
  apiBaseUrl,
  snapshotPollMs: 15_000,
  snapshotRetryMs: 30_000,
  maxWatchlistItems: 50,
} as const
