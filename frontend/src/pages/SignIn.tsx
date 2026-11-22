import { useState, type FormEvent } from 'react'
import { api, errorMessage, type Identity } from '../services/admin'

export function SignIn({ setup, onLogin }: { setup: boolean; onLogin: (identity: Identity) => void }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    setError('')
    setBusy(true)
    try {
      const identity = await api<Identity>('auth/login', {
        method: 'POST', body: { username: fields.get('username'), password: fields.get('password') },
      })
      const session = await api<{ administrator: Identity | null }>('auth/session')
      if (!session.administrator) throw new Error('The browser did not retain the session cookie. Check the HTTPS or local HTTP configuration.')
      onLogin(identity)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto mt-12 max-w-md px-5">
      <h1 className="mb-5 text-3xl font-semibold">Kindle Dashboard</h1>
      {setup ? <section className="panel">
        <h2 className="text-xl font-semibold">Set up the administrator</h2>
        <p className="mt-3">Run this from the project directory on Dashboard NAS, then reload this page.</p>
        <code className="mt-3 block break-words rounded bg-slate-100 p-3">PYTHONPATH=backend .venv/bin/python -m app.setup_admin admin</code>
      </section> : <form className="panel grid gap-4" onSubmit={submit}>
        <h2 className="text-xl font-semibold">Administrator sign-in</h2>
        <label>Username<input className="field" name="username" autoComplete="username" required maxLength={64} /></label>
        <label>Password<input className="field" name="password" type="password" autoComplete="current-password" required maxLength={256} /></label>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>}
      <a className="mt-4 inline-block underline" href="/kindle/test">Kindle browser test</a>
    </main>
  )
}
