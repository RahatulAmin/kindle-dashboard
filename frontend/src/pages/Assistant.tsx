import { useState, type FormEvent } from 'react'
import { api, errorMessage, useResource } from '../services/admin'

type Briefing = { title: string; lines: string[]; updated_at: string }
type AuditRow = {
  id: number
  token_id: number
  token_name: string
  action: string
  resource_type: string
  resource_id: number
  timestamp: string
  changed_fields: string[]
}

export function BriefingPage({ token }: { token: string }) {
  const briefing = useResource<Briefing | null>('briefing')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  async function clear() {
    setBusy(true)
    setFeedback('')
    try {
      await api('briefing', { method: 'DELETE', token })
      briefing.setData(null)
    } catch (reason) {
      setFeedback(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }
  return <>
    <h1 className="page-title">Briefing</h1>
    <section className="panel mt-5 space-y-3">
      {briefing.loading && <p role="status">Loading briefing…</p>}
      {briefing.error && <p role="alert" className="error">{briefing.error} <button onClick={briefing.reload}>Retry</button></p>}
      {feedback && <p role="alert" className="error">{feedback}</p>}
      {briefing.data === null && <p>No briefing has been published.</p>}
      {briefing.data && <>
        <h2 className="break-words text-xl font-semibold">{briefing.data.title}</h2>
        <p className="text-sm text-slate-600">
          Updated <time dateTime={briefing.data.updated_at}>{new Date(briefing.data.updated_at).toLocaleString()}</time>
        </p>
        <ul className="space-y-1 break-words">
          {briefing.data.lines.map((line, index) => <li key={index}>{line}</li>)}
        </ul>
        <button className="action" disabled={busy} onClick={() => void clear()}>{busy ? 'Clearing…' : 'Clear briefing'}</button>
      </>}
    </section>
  </>
}

export function AuditHistory() {
  const [filters, setFilters] = useState('')
  const [before, setBefore] = useState<number>()
  const query = new URLSearchParams(filters)
  if (before !== undefined) query.set('before_id', String(before))
  const history = useResource<AuditRow[]>(`audit?${query.toString()}`)
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = new URLSearchParams()
    for (const [name, value] of new FormData(event.currentTarget)) {
      if (value) next.set(name, String(value))
    }
    setBefore(undefined)
    setFilters(next.toString())
    history.reload()
  }
  return <>
    <h1 className="page-title">API Audit</h1>
    <form className="panel mt-5 grid gap-3 sm:grid-cols-2" onSubmit={filter}>
      <label>Token ID<input className="field" type="number" name="token_id" min="1" /></label>
      <label>Action<select className="field" name="action">
        <option value="">All actions</option>
        {['create', 'upsert', 'update', 'delete', 'replace'].map(action => <option key={action}>{action}</option>)}
      </select></label>
      <label>From date (UTC)<input className="field" type="date" name="date_from" /></label>
      <label>Through date (UTC)<input className="field" type="date" name="date_to" /></label>
      <button className="action justify-self-start">Apply filters</button>
    </form>
    <section className="panel mt-5 space-y-3">
      {history.loading && <p role="status">Loading audit history…</p>}
      {history.error && <p role="alert" className="error">{history.error} <button onClick={history.reload}>Retry</button></p>}
      {!history.loading && !history.error && history.data && <>
        {history.data.length === 0 && <p>No matching audit entries.</p>}
        {history.data.length > 0 && <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead><tr>{['Time (UTC)', 'Token', 'Action', 'Resource', 'Changed fields'].map(text =>
              <th className="p-2" scope="col" key={text}>{text}</th>)}</tr></thead>
            <tbody>{history.data.map(row => <tr key={row.id} className="border-t border-slate-200">
              <td className="p-2"><time dateTime={row.timestamp}>{row.timestamp.slice(0, 19).replace('T', ' ')}</time></td>
              <td className="p-2 wrap-anywhere">{row.token_name} (#{row.token_id})</td>
              <td className="p-2">{row.action}</td>
              <td className="p-2">{row.resource_type} #{row.resource_id}</td>
              <td className="p-2">{row.changed_fields.join(', ') || '—'}</td>
            </tr>)}</tbody>
          </table>
        </div>}
        <div className="flex gap-3">
          {before !== undefined && <button className="action" onClick={() => { setBefore(undefined); history.reload() }}>Newest</button>}
          {history.data.length === 50 && <button className="action" onClick={() => {
            setBefore(history.data?.at(-1)?.id)
            history.reload()
          }}>Older entries</button>}
        </div>
      </>}
    </section>
  </>
}
