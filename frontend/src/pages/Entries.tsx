import { useMemo, useRef, useState, type FormEvent } from 'react'
import { api, errorMessage, useResource, type Entry, type EntryInput, type Priority } from '../services/admin'

type Kind = 'tasks' | 'deadlines'
const priorityRank = { high: 0, normal: 1, low: 2 }

function entryInput(entry: Entry, kind: Kind): EntryInput {
  const { title, description, priority, due_date, completed, kindle_visible } = entry
  return {
    title, description, priority, due_date, completed, kindle_visible,
    ...(kind === 'tasks' ? { position: entry.position } : { due_time: entry.due_time, archived: entry.archived }),
  }
}

function countdown(days: number) {
  if (days === 0) return 'Due today'
  const duration = Math.abs(days) === 1 ? '1 day' : Math.abs(days) + ' days'
  return days < 0 ? duration + ' overdue' : 'Due in ' + duration
}

export function Entries({ kind, token }: { kind: Kind; token: string }) {
  const singular = kind === 'tasks' ? 'task' : 'deadline'
  const task = kind === 'tasks'
  const resource = useResource<Entry[]>(kind)
  const [edit, setEdit] = useState<Entry | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState('active')
  const [sort, setSort] = useState('manual')
  const [query, setQuery] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const editor = useRef<HTMLHeadingElement>(null)
  const records = useMemo(() => {
    const items = (resource.data || []).filter(entry => {
      if (filter === 'active' && (entry.completed || entry.archived)) return false
      if (filter === 'completed' && (!entry.completed || entry.archived)) return false
      if (filter === 'archived' && !entry.archived) return false
      return (entry.title + ' ' + entry.description).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
    })
    if (task && sort === 'priority') return items.sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority])
    if (task && sort === 'due') return items.sort((a, b) => (a.due_date || '9999-99-99').localeCompare(b.due_date || '9999-99-99'))
    if (task && sort === 'title') return items.sort((a, b) => a.title.localeCompare(b.title))
    return items
  }, [resource.data, filter, sort, query, task])

  async function mutate(action: () => Promise<unknown>, message: string, closeForm = false) {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      await action()
      resource.reload()
      setNotice(message)
      if (closeForm) {
        setShowForm(false)
        setEdit(null)
      }
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  function openEditor(item: Entry | null) {
    setEdit(item)
    setShowForm(true)
    setError('')
    requestAnimationFrame(() => editor.current?.focus())
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const body: EntryInput = {
      title: String(fields.get('title') || ''), description: String(fields.get('description') || ''),
      priority: fields.get('priority') as Priority, due_date: String(fields.get('due_date') || '') || null,
      completed: fields.has('completed'), kindle_visible: fields.has('kindle_visible'),
      ...(task ? { position: Number(fields.get('position')) } : {
        due_time: String(fields.get('due_time') || '') || null, archived: fields.has('archived'),
      }),
    }
    void mutate(() => api(edit ? kind + '/' + edit.id : kind, {
      token, method: edit ? 'PUT' : 'POST', body,
    }), edit ? 'Changes saved.' : 'Entry added.', true)
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">{task ? 'Tasks' : 'Deadlines'}</h1>
        <button type="button" className="primary" disabled={saving || resource.loading} onClick={() => openEditor(null)}>Add {singular}</button>
      </div>
      {error && <p role="alert" className="error mt-4">{error}</p>}
      {notice && <p role="status" className="mt-4">{notice}</p>}
      {showForm && <section className="panel mt-5">
        <h2 ref={editor} tabIndex={-1} className="text-xl font-semibold">{edit ? 'Edit ' : 'Add '}{singular}</h2>
        <form key={edit?.id ?? 'new'} className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={save}>
          <label className="sm:col-span-2">Title<input className="field" name="title" defaultValue={edit?.title} required maxLength={160} /></label>
          <label className="sm:col-span-2">Description<textarea className="field" name="description" defaultValue={edit?.description} maxLength={4000} rows={3} /></label>
          <label>Priority<select className="field" name="priority" defaultValue={edit?.priority ?? 'normal'}>
            <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
          </select></label>
          <label>Due date<input className="field" name="due_date" type="date" defaultValue={edit?.due_date ?? ''} required={!task} /></label>
          {task
            ? <label>Manual position<input className="field" name="position" type="number" min="0" max="999999" required defaultValue={edit?.position ?? Math.min(999999, Math.max(-1, ...(resource.data || []).map(item => item.position ?? 0)) + 1)} /><small>Lower numbers appear first.</small></label>
            : <label>Time in Toronto (optional)<input className="field" name="due_time" type="time" defaultValue={edit?.due_time?.slice(0, 5)} /></label>}
          <div className="flex flex-wrap items-center gap-3">
            <label><input name="completed" type="checkbox" defaultChecked={edit?.completed} /> Complete</label>
            {!task && <label><input name="archived" type="checkbox" defaultChecked={edit?.archived} /> Archived</label>}
            <label><input name="kindle_visible" type="checkbox" defaultChecked={edit?.kindle_visible ?? true} /> Show on Kindle</label>
          </div>
          <div className="flex gap-2 sm:col-span-2">
            <button type="submit" className="primary" disabled={saving}>{saving ? 'Saving…' : 'Save ' + singular}</button>
            <button type="button" className="action" disabled={saving} onClick={() => { setShowForm(false); setEdit(null) }}>Cancel</button>
          </div>
        </form>
      </section>}
      <section className="panel mt-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <label>Search<input className="field" type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <label>Status<select className="field" value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="active">Active</option><option value="completed">Completed</option>
            {!task && <option value="archived">Archived</option>}
            <option value="all">All</option>
          </select></label>
          {task && <label>Sort by<select className="field" value={sort} onChange={event => setSort(event.target.value)}>
            <option value="manual">Manual order</option><option value="priority">Priority</option>
            <option value="due">Due date</option><option value="title">Title</option>
          </select></label>}
        </div>
        {resource.loading && <p role="status" className="mt-4">Loading {kind}…</p>}
        {resource.error && <p role="alert" className="error mt-4">{resource.error} <button className="underline" onClick={resource.reload}>Retry</button></p>}
        {!resource.loading && !resource.error && !records.length && <p className="mt-5 text-slate-600">No {kind} match this view.</p>}
        <ul className="mt-3 divide-y divide-slate-200">
          {records.map(entry => <li key={entry.id} className="py-4">
            <h2 className="wrap-anywhere font-semibold">{entry.title}</h2>
            {entry.description && <p className="wrap-anywhere whitespace-pre-wrap text-slate-600">{entry.description}</p>}
            <p className="mt-1 text-sm text-slate-700">
              {entry.priority} priority · {entry.due_date || 'No due date'}{entry.due_time && ' at ' + entry.due_time.slice(0, 5)}
              {entry.days_until !== undefined && ' · ' + countdown(entry.days_until)}
              {entry.archived ? ' · Archived' : entry.completed ? ' · Completed' : ''}
              {' · '}{entry.kindle_visible ? 'Kindle visible' : 'Kindle hidden'}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="action" disabled={saving} onClick={() => openEditor(entry)}>Edit</button>
              <button type="button" className="action" disabled={saving} onClick={() => void mutate(() => api(kind + '/' + entry.id, {
                method: 'PUT', token, body: { ...entryInput(entry, kind), completed: !entry.completed },
              }), entry.completed ? 'Entry reopened.' : 'Entry completed.')}>{entry.completed ? 'Reopen' : 'Complete'}</button>
              {!task && <button type="button" className="action" disabled={saving} onClick={() => void mutate(() => api(kind + '/' + entry.id, {
                method: 'PUT', token, body: { ...entryInput(entry, kind), archived: !entry.archived },
              }), entry.archived ? 'Entry restored.' : 'Entry archived.')}>{entry.archived ? 'Restore' : 'Archive'}</button>}
              <button type="button" className="action text-red-800" disabled={saving} onClick={() => {
                if (window.confirm('Delete this ' + singular + '?')) void mutate(
                  () => api(kind + '/' + entry.id, { method: 'DELETE', token }), 'Entry deleted.', edit?.id === entry.id,
                )
              }}>Delete</button>
            </div>
          </li>)}
        </ul>
      </section>
    </>
  )
}
