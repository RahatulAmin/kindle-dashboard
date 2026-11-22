import { useResource, type Weather } from '../services/admin'

export function Overview() {
  const counts = useResource<{ open_tasks: number; active_deadlines: number }>('overview')
  const forecast = useResource<Weather>('weather')
  const health = useResource<{ status: string; database: string }>('health')
  const weather = forecast.data?.weather

  return (
    <>
      <h1 className="page-title">Overview</h1>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <section className="panel">
          <h2 className="text-xl font-semibold">Productivity</h2>
          {counts.loading && <p role="status" className="mt-3">Loading dashboard data…</p>}
          {counts.error && <p role="alert" className="error mt-3">{counts.error} <button className="underline" onClick={counts.reload}>Retry</button></p>}
          {counts.data && <ul className="mt-3 space-y-2">
            <li><a className="underline" href="#/tasks">{counts.data.open_tasks} open tasks</a></li>
            <li><a className="underline" href="#/deadlines">{counts.data.active_deadlines} active deadlines</a></li>
          </ul>}
        </section>
        <section className="panel">
          <h2 className="text-xl font-semibold">Weather</h2>
          {forecast.loading && <p role="status" className="mt-3">Checking Open-Meteo…</p>}
          {forecast.error && <p role="alert" className="error mt-3">{forecast.error} <button className="underline" onClick={forecast.reload}>Retry</button></p>}
          {forecast.data && <p className="mt-3 font-medium">{forecast.data.location}</p>}
          {weather?.status === 'unavailable' && <p className="mt-1">Weather is unavailable. Check the location and internet connection.</p>}
          {weather && weather.temperature !== null && <>
            <p className="mt-1 text-2xl">{Math.round(weather.temperature)} °C · {weather.condition}</p>
            <p className="mt-1">High {weather.high} °C · Low {weather.low} °C</p>
            {weather.updated_at && <p className="mt-2 text-sm">Last updated {new Date(weather.updated_at).toLocaleString()}{weather.status === 'stale' && ' · Stale'}</p>}
          </>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="action" onClick={forecast.reload} disabled={forecast.loading}>Check weather</button>
            <a className="text-sm underline" href="https://open-meteo.com/">Weather data by Open-Meteo</a>
          </div>
        </section>
        <section className="panel">
          <h2 className="text-xl font-semibold">Dashboard NAS connection</h2>
          <p className="mt-3" role="status">{health.loading ? 'Checking connection…' : health.error ? 'Health check failed.' : 'Backend and SQLite are available.'}</p>
          <button className="action mt-3" onClick={health.reload} disabled={health.loading}>Check again</button>
        </section>
      </div>
    </>
  )
}
