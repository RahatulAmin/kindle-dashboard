import { useState, type FormEvent } from 'react'
import { api, errorMessage, useResource, type Preferences, type Widget } from '../services/admin'

const widgetNames: Record<Widget['key'], string> = {
  datetime: 'Date and time', weather: 'Weather', tasks: 'Tasks', deadlines: 'Deadlines',
  pomodoro: 'Pomodoro (planned)', nas: 'NAS status (planned)', briefing: 'Briefing',
}

function GeneralForm({ initial, save, busy }: {
  initial: Preferences; save: (prefs: Preferences) => Promise<void>; busy: boolean;
}) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    void save({
      ...initial, dashboard_title: String(data.get('title')),
      kindle_data_enabled: data.has('sharing'),
      kindle_refresh_seconds: Number(data.get('refresh')),
      weather: {
        name: String(data.get('location')), latitude: Number(data.get('latitude')),
        longitude: Number(data.get('longitude')), timezone: String(data.get('timezone')),
      },
    })
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <section className="panel grid gap-4">
        <h2 className="text-xl font-semibold">Kindle display</h2>
        <label>Dashboard title<input className="field" name="title" defaultValue={initial.dashboard_title} required maxLength={160} /></label>
        <label>Refresh interval in seconds<input className="field" name="refresh" type="number" min="30" max="3600" defaultValue={initial.kindle_refresh_seconds} required /></label>
        <label><input type="checkbox" name="sharing" defaultChecked={initial.kindle_data_enabled} /> Show dashboard data on the Kindle page</label>
        <p className="text-sm text-slate-700">Anyone who can reach the Kindle page can see shared widget data. Share only on your trusted network.</p>
      </section>
      <section className="panel grid gap-4 sm:grid-cols-2">
        <h2 className="text-xl font-semibold sm:col-span-2">Weather location</h2>
        <label className="sm:col-span-2">Location name<input className="field" name="location" defaultValue={initial.weather.name} required maxLength={160} /></label>
        <label>Latitude<input className="field" name="latitude" type="number" step="any" min="-90" max="90" defaultValue={initial.weather.latitude} required /></label>
        <label>Longitude<input className="field" name="longitude" type="number" step="any" min="-180" max="180" defaultValue={initial.weather.longitude} required /></label>
        <label className="sm:col-span-2">IANA timezone<input className="field" name="timezone" defaultValue={initial.weather.timezone} required maxLength={64} /></label>
      </section>
      <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</button>
    </form>
  )
}

function WidgetForm({ initial, save, busy }: {
  initial: Preferences; save: (prefs: Preferences) => Promise<void>; busy: boolean;
}) {
  const [widgets, setWidgets] = useState(initial.widgets)

  function change(key: Widget['key'], update: Partial<Widget>) {
    setWidgets(items => items.map(item => item.key === key ? { ...item, ...update } : item))
  }

  function move(index: number, direction: number) {
    setWidgets(items => {
      const next = [...items]
      const target = index + direction
      next[index] = items[target]
      next[target] = items[index]
      return next
    })
  }

  return (
    <form className="panel grid gap-4" onSubmit={event => {
      event.preventDefault()
      void save({ ...initial, widgets })
    }}>
      <p className="text-slate-700">The portrait dashboard follows this order. Briefing sits below weather on landscape Todo.</p>
      <ol className="divide-y divide-slate-200">
        {widgets.map((widget, index) => <li key={widget.key} className="grid gap-3 py-4 sm:grid-cols-[1fr_8rem_auto]">
          <label className="self-center"><input type="checkbox" checked={widget.visible} onChange={event => change(widget.key, { visible: event.target.checked })} /> {widgetNames[widget.key]}</label>
          <label>{widget.key === 'tasks' || widget.key === 'deadlines' ? 'Item limit' : 'Display limit'}
            <input className="field" type="number" min="1" max={['datetime', 'weather', 'briefing'].includes(widget.key) ? '1' : '12'} required value={widget.limit || ''} onChange={event => change(widget.key, { limit: Number(event.target.value) })} />
          </label>
          <div className="flex items-end gap-2">
            <button type="button" className="action" aria-label={'Move ' + widgetNames[widget.key] + ' up'} disabled={index === 0} onClick={() => move(index, -1)}>Up</button>
            <button type="button" className="action" aria-label={'Move ' + widgetNames[widget.key] + ' down'} disabled={index === widgets.length - 1} onClick={() => move(index, 1)}>Down</button>
          </div>
        </li>)}
      </ol>
      <button className="primary justify-self-start" disabled={busy}>{busy ? 'Saving…' : 'Save widgets'}</button>
    </form>
  )
}

export function PreferencesPage({ widgets, token }: { widgets: boolean; token: string }) {
  const prefs = useResource<Preferences>('settings')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const Form = widgets ? WidgetForm : GeneralForm

  async function save(body: Preferences) {
    setBusy(true)
    setMessage('')
    setError('')
    try {
      prefs.setData(await api<Preferences>('settings', { method: 'PUT', token, body }))
      setMessage('Preferences saved.')
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1 className="page-title">{widgets ? 'Widgets' : 'Settings'}</h1>
      <div className="mt-5 space-y-4">
        {prefs.loading && <p role="status">Loading preferences…</p>}
        {(prefs.error || error) && <p role="alert" className="error">{prefs.error || error} {prefs.error && <button className="underline" onClick={prefs.reload}>Retry</button>}</p>}
        {message && <p role="status">{message}</p>}
        {prefs.data && <Form initial={prefs.data} save={save} busy={busy} />}
      </div>
    </>
  )
}

export function Display() {
  const prefs = useResource<Preferences>('settings')
  return (
    <>
      <h1 className="page-title">Display</h1>
      <section className="panel mt-5 space-y-4">
        {prefs.loading && <p role="status">Loading display settings…</p>}
        {prefs.error && <p role="alert" className="error">{prefs.error} <button className="underline" onClick={prefs.reload}>Retry</button></p>}
        {prefs.data && <p>{prefs.data.kindle_data_enabled ? 'The Kindle page is showing dashboard data.' : 'The Kindle page is showing the test image. Enable data sharing in Settings to show dashboard widgets.'}</p>}
        <div className="flex flex-wrap gap-2">
          <a className="action" href="/kindle">Open Kindle display</a>
          <a className="action" href="/kindle/test">Open browser diagnostic</a>
          <a className="action" href="#/settings">Display settings</a>
        </div>
      </section>
    </>
  )
}
