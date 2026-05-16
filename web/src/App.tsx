import { useEffect, useState } from 'react'

type BackendStatus = 'checking' | 'online' | 'offline'

const API_URL = 'http://localhost:8000'

export default function App() {
  const [status, setStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    let cancelled = false
    fetch(`${API_URL}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(() => {
        if (!cancelled) setStatus('online')
      })
      .catch(() => {
        if (!cancelled) setStatus('offline')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const badge =
    status === 'online'
      ? { text: '✓ Backend connected', cls: 'text-emerald-300 border-emerald-400/40 bg-emerald-400/10' }
      : status === 'offline'
        ? { text: '✗ Backend offline', cls: 'text-rose-300 border-rose-400/40 bg-rose-400/10' }
        : { text: '… Checking backend', cls: 'text-slate-300 border-slate-400/30 bg-slate-400/10' }

  return (
    <div className="relative min-h-full w-full overflow-hidden">
      <div
        className={`absolute top-4 right-4 rounded-full border px-3 py-1 text-xs font-medium backdrop-blur ${badge.cls}`}
      >
        {badge.text}
      </div>

      <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center px-6 py-16">
        <header className="mb-12 text-center">
          <h1 className="bg-gradient-to-b from-white to-blue-300 bg-clip-text text-5xl font-semibold tracking-tight text-transparent sm:text-6xl">
            Tab Constellation
          </h1>
          <p className="mt-4 text-base text-slate-400 sm:text-lg">
            Your browsing history as a navigable cognitive map
          </p>
        </header>

        <section
          aria-label="Constellation view placeholder"
          className="flex h-[420px] w-full items-center justify-center rounded-2xl border-2 border-dashed border-slate-700 bg-slate-900/30 text-sm text-slate-500"
        >
          Constellation view &mdash; coming soon
        </section>
      </main>
    </div>
  )
}
