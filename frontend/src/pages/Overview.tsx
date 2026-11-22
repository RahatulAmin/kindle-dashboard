import { useEffect, useState } from 'react'
import { readHealth, type Connection } from '../services/health'

const statuses = {
  checking: ['Checking connection', 'Waiting for a response from Dashboard NAS.'],
  connected: ['Connected', 'The backend and SQLite database are available.'],
  degraded: ['Database unavailable', 'The backend responded. Check its database connection.'],
  unreachable: ['Backend unavailable', 'The health endpoint could not be reached or returned an unexpected response.'],
} satisfies Record<Connection, [string, string]>

export function Overview() {
  const [connection, setConnection] = useState<Connection>('checking')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let stopped = false
    const timeout = window.setTimeout(() => controller.abort(), 5000)
    readHealth(controller.signal)
      .then(status => { if (!stopped) setConnection(status) })
      .catch(() => { if (!stopped) setConnection('unreachable') })
      .finally(() => window.clearTimeout(timeout))
    return () => {
      stopped = true
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  const [status, description] = statuses[connection]
  return (
    <>
      <h1 className="text-4xl font-semibold tracking-tight">Overview</h1>
      <div className="mt-7 grid gap-4 lg:grid-cols-2">
        <section className="panel">
          <h2 className="text-lg font-semibold">Backend connection</h2>
          <div role="status" className="mt-4">
            <p className="font-semibold text-teal-800">{status}</p>
            <p className="mt-1 text-slate-600">{description}</p>
          </div>
          <button type="button" className="action mt-5" disabled={connection === 'checking'} onClick={() => {
            setConnection('checking')
            setAttempt(value => value + 1)
          }}>Check again</button>
        </section>
        <section className="panel">
          <h2 className="text-lg font-semibold">Kindle test display</h2>
          <p className="mt-4 text-slate-600">Preview a grayscale image with the current server date and time.</p>
          <a className="action mt-5 inline-block" href="/kindle">Open test display</a>
        </section>
      </div>
    </>
  )
}
