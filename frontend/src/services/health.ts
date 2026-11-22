export type Connection = 'checking' | 'connected' | 'degraded' | 'unreachable'

export async function readHealth(signal: AbortSignal): Promise<Connection> {
  const response = await fetch('/api/v1/health', { signal, cache: 'no-store' })
  const { data } = await response.json()
  if (response.ok && data?.status === 'ok' && data.database === 'available') return 'connected'
  if (response.status === 503 && data?.database === 'unavailable') return 'degraded'
  return 'unreachable'
}
