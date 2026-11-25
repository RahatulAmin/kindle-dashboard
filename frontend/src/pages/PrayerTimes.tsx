import { useEffect, useState, type FormEvent } from 'react'
import { api, errorMessage, useResource } from '../services/admin'

const names = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'] as const
type Prayer = typeof names[number]
type Settings = {
  enabled: boolean
  city: string
  country: string
  method: number
  school: 0 | 1 | null
  latitude_adjustment: number
  adjustments: Record<Lowercase<Prayer>, number>
}
type PrayerStatus = {
  preferences: Settings
  methods: Record<string, string>
  date: string
  today: Record<Prayer, string>
  last_updated_at: string | null
}

export function PrayerTimes({ token }: { token: string }) {
  const { data, setData, error, loading, reload } = useResource<PrayerStatus>('prayer-times')
  const [draft, setDraft] = useState<Settings>()
  const [busy, setBusy] = useState('')
  const [feedback, setFeedback] = useState({ message: '', error: false })
  const value = draft ?? data?.preferences
  const dirty = draft !== undefined
  const awaitingSchedule = data?.preferences.school != null && data.today.Fajr === '--:--'

  useEffect(() => {
    if (!awaitingSchedule || busy) return
    const controller = new AbortController()
    const interval = window.setInterval(() => {
      void api<PrayerStatus>('prayer-times', { signal: controller.signal })
        .then(result => { if (!controller.signal.aborted) setData(result) })
        .catch(() => undefined)
    }, 15000)
    return () => {
      controller.abort()
      window.clearInterval(interval)
    }
  }, [awaitingSchedule, busy, setData])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!value) return
    setBusy('save')
    setFeedback({ message: '', error: false })
    try {
      setData(await api<PrayerStatus>('prayer-times', { method: 'PUT', body: value, token }))
      setDraft(undefined)
      setFeedback({ message: 'Prayer settings saved.', error: false })
    } catch (reason) {
      setFeedback({ message: errorMessage(reason), error: true })
    } finally {
      setBusy('')
    }
  }

  async function refresh() {
    setBusy('refresh')
    setFeedback({ message: '', error: false })
    try {
      setData(await api<PrayerStatus>('prayer-times/refresh', { method: 'POST', token }))
      setFeedback({ message: 'Schedules refreshed.', error: false })
    } catch (reason) {
      setFeedback({ message: errorMessage(reason), error: true })
      try {
        setData(await api<PrayerStatus>('prayer-times'))
      } catch {
        // Keep the most recent preview when the NAS is temporarily unreachable.
      }
    } finally {
      setBusy('')
    }
  }

  return <>
    <h1 className="page-title">Prayer Times</h1>
    {loading && <p className="mt-5" role="status">Loading prayer settings…</p>}
    {error && <div className="panel mt-5">
      <p className="error" role="alert">{error}</p>
      <button className="action mt-3" onClick={reload}>Retry</button>
    </div>}
    {data && value && !loading && !error && <>
      <form className="panel mt-5 space-y-5" onSubmit={submit}>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={value.enabled}
            onChange={event => setDraft({ ...value, enabled: event.target.checked })} />
          Show prayer times on the Kindle
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label>City
            <input className="field" required maxLength={90} value={value.city}
              onChange={event => setDraft({ ...value, city: event.target.value })} />
          </label>
          <label>Country
            <input className="field" required maxLength={90} value={value.country}
              onChange={event => setDraft({ ...value, country: event.target.value })} />
          </label>
          <label>Calculation method
            <select className="field" value={value.method} onChange={event => setDraft({ ...value, method: Number(event.target.value) })}>
              {Object.entries(data.methods).map(([number, name]) => <option key={number} value={number}>{name}</option>)}
            </select>
          </label>
          <label>Asr calculation
            <select className="field" required={value.enabled} value={value.school ?? ''}
              onChange={event => setDraft({ ...value, school: event.target.value === '' ? null : Number(event.target.value) as 0 | 1 })}>
              <option value="">Select Standard or Hanafi</option>
              <option value="0">Standard</option>
              <option value="1">Hanafi</option>
            </select>
          </label>
          <label>High-latitude adjustment
            <select className="field" value={value.latitude_adjustment}
              onChange={event => setDraft({ ...value, latitude_adjustment: Number(event.target.value) })}>
              <option value={1}>Middle of the night</option>
              <option value={2}>One seventh</option>
              <option value={3}>Angle based</option>
            </select>
          </label>
        </div>
        <fieldset>
          <legend className="font-medium">Adjustments in minutes</legend>
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {names.map(name => {
              const key = name.toLowerCase() as Lowercase<Prayer>
              return <label key={name}>{name}
                <input className="field" type="number" min={-120} max={120} step={1} value={value.adjustments[key]}
                  onChange={event => setDraft({ ...value, adjustments: { ...value.adjustments, [key]: Number(event.target.value) } })} />
              </label>
            })}
          </div>
        </fieldset>
        <button className="primary" disabled={!dirty || !!busy}>{busy === 'save' ? 'Saving…' : 'Save settings'}</button>
      </form>
      <section className="panel mt-5" aria-labelledby="prayer-preview">
        <h2 id="prayer-preview" className="text-lg font-semibold">Today’s prayer times</h2>
        <p className="mt-1 text-sm text-slate-600">{data.date} · America/Toronto</p>
        <dl className="my-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {names.map(name => <div key={name}>
            <dt>{name}</dt><dd className="font-semibold tabular-nums">{data.today[name]}</dd>
          </div>)}
        </dl>
        <p className="text-sm text-slate-600">
          Last successful update {data.last_updated_at ? new Date(data.last_updated_at).toLocaleString() : 'unavailable'}
        </p>
        <button type="button" className="action mt-3" disabled={dirty || !!busy || data.preferences.school === null}
          onClick={() => void refresh()}>{busy === 'refresh' ? 'Refreshing…' : 'Refresh schedules'}</button>
      </section>
      {feedback.message && <p className={feedback.error ? 'error mt-4' : 'mt-4'}
        role={feedback.error ? 'alert' : 'status'}>{feedback.message}</p>}
    </>}
  </>
}
