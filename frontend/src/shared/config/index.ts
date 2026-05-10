export const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
).replace(/\/$/, '')

export const appConfig = {
  apiBaseUrl,
  barsPollMs: 10_000,
  barsRetryMs: 5_000,
  snapshotPollMs: 10_000,
  snapshotRetryMs: 5_000,
  maxWatchlistItems: 50,
} as const
