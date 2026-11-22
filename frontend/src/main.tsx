import { useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { AdminShell, pages, type Page } from './layouts/AdminShell'
import { Overview } from './pages/Overview'
import './styles.css'

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

function currentPage(): Page {
  const key = window.location.hash.slice(2)
  return Object.hasOwn(pages, key) ? key as Page : 'overview'
}

function App() {
  const page = useSyncExternalStore(subscribe, currentPage)
  return (
    <AdminShell page={page}>
      {page === 'overview' ? <Overview /> : (
        <>
          <h1 className="text-4xl font-semibold tracking-tight">{pages[page]}</h1>
          <p className="panel mt-7 text-slate-600">This section is planned for a later phase.</p>
        </>
      )}
    </AdminShell>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
