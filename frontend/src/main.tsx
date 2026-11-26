import { useEffect, useState, useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { AdminShell, pages, type Page } from './layouts/AdminShell'
import { AuditHistory, BriefingPage } from './pages/Assistant'
import { Entries } from './pages/Entries'
import { Overview } from './pages/Overview'
import { PrayerTimes } from './pages/PrayerTimes'
import { Display, PreferencesPage } from './pages/Preferences'
import { SignIn } from './pages/SignIn'
import { api, errorMessage, useResource, type Identity, type Session } from './services/admin'
import './styles.css'

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

function currentPage(): Page {
  const key = window.location.hash.slice(2)
  return Object.hasOwn(pages, key) ? key as Page : 'overview'
}

function Content({ page, token }: { page: Page; token: string }) {
  switch (page) {
    case 'overview': return <Overview />
    case 'tasks':
    case 'deadlines': return <Entries key={page} kind={page} token={token} />
    case 'settings':
    case 'widgets': return <PreferencesPage key={page} widgets={page === 'widgets'} token={token} />
    case 'display': return <Display />
    case 'briefing': return <BriefingPage token={token} />
    case 'audit': return <AuditHistory />
    case 'prayer-times': return <PrayerTimes token={token} />
    default: return <>
      <h1 className="page-title">{pages[page]}</h1>
      <p className="panel mt-5">This section is planned for a later phase.</p>
    </>
  }
}

function App() {
  const page = useSyncExternalStore(subscribe, currentPage)
  const { data, error, loading, reload, setData } = useResource<Session>('auth/session')
  const [logoutError, setLogoutError] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)

  useEffect(() => {
    const expire = () => setData(current => current && { ...current, administrator: null })
    window.addEventListener('admin-session-expired', expire)
    return () => window.removeEventListener('admin-session-expired', expire)
  }, [setData])

  if (loading) return <p className="p-6" role="status">Checking administrator session…</p>
  if (error || !data) return <main className="p-6">
    <p role="alert" className="error">{error || 'Session status is unavailable.'}</p>
    <button className="action mt-3" onClick={reload}>Retry</button>
  </main>
  const identity = data.administrator
  if (!identity) return <SignIn setup={data.setup_required} onLogin={(administrator: Identity) => {
    setLogoutError('')
    setData({ setup_required: false, administrator })
  }} />

  async function logout(token: string) {
    setLoggingOut(true)
    setLogoutError('')
    try {
      await api('auth/logout', { method: 'POST', token })
      setData({ setup_required: false, administrator: null })
    } catch (reason) {
      setLogoutError(errorMessage(reason))
    } finally {
      setLoggingOut(false)
    }
  }

  return <AdminShell page={page} account={<div className="mt-6 border-t border-slate-700 pt-4">
    <p className="wrap-anywhere text-sm text-slate-300">{identity.username}</p>
    <button type="button" disabled={loggingOut} className="mt-2 min-h-10 rounded border border-slate-500 px-3 text-sm" onClick={() => void logout(identity.csrf_token)}>Sign out</button>
    {logoutError && <p className="mt-2 text-sm text-red-200" role="alert">{logoutError}</p>}
  </div>}>
    <Content page={page} token={identity.csrf_token} />
  </AdminShell>
}

createRoot(document.getElementById('root')!).render(<App />)
