import { useCallback, useEffect, useState } from 'react'

export type Identity = { username: string; csrf_token: string }
export type Session = { administrator: Identity | null; setup_required: boolean }
export type Priority = 'low' | 'normal' | 'high'
export type EntryInput = {
  title: string; description: string; priority: Priority; due_date: string | null;
  completed: boolean; kindle_visible: boolean; position?: number; due_time?: string | null;
  archived?: boolean;
}
export type Entry = EntryInput & { id: number; created_at: string; updated_at: string; days_until?: number }
export type Widget = { key: 'datetime' | 'weather' | 'tasks' | 'deadlines' | 'pomodoro' | 'nas'; visible: boolean; limit: number }
export type Preferences = {
  kindle_data_enabled: boolean; dashboard_title: string; kindle_refresh_seconds: number;
  weather: { name: string; latitude: number; longitude: number; timezone: string };
  widgets: Widget[];
}
export type Weather = {
  location: string;
  weather: {
    status: 'fresh' | 'stale' | 'unavailable'; temperature: number | null;
    condition: string | null; high: number | null; low: number | null; updated_at: string | null;
  };
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const headers = new Headers()
  if (options.body !== undefined) headers.set('Content-Type', 'application/json')
  if (path === 'auth/login') headers.set('X-Kindle-Admin', '1')
  if (options.token) headers.set('X-CSRF-Token', options.token)
  const response = await fetch('/api/v1/' + path, {
    method: options.method, signal: options.signal, headers, cache: 'no-store',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  if (response.status === 204) return undefined as T
  const result = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('auth/login')) {
      window.dispatchEvent(new Event('admin-session-expired'))
    }
    throw new Error(result.error?.message || 'The server returned an unexpected response.')
  }
  return result.data as T
}

export function errorMessage(error: unknown) {
  if (error instanceof TypeError) return 'Could not reach Dashboard NAS. Check the connection and try again.'
  return error instanceof Error ? error.message : 'Something went wrong. Try again.'
}

export function useResource<T>(path: string) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const reload = useCallback(() => {
    setLoading(true)
    setError('')
    setRevision(current => current + 1)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    api<T>(path, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setData(result) })
      .catch(reason => { if (!controller.signal.aborted) setError(errorMessage(reason)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [path, revision])

  return { data, setData, error, loading, reload }
}
