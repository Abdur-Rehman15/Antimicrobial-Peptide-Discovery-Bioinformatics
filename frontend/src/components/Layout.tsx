import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api/client'

type Theme = 'light' | 'dark' | 'system'

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem('amp-theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* storage can be blocked; fall back to the system setting */
  }
  return 'system'
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try {
      if (theme === 'system') localStorage.removeItem('amp-theme')
      else localStorage.setItem('amp-theme', theme)
    } catch {
      /* ignore */
    }
  }, [theme])
  return [theme, setTheme] as const
}

/** Polls /health so a stopped backend is announced instead of leaving pages blank. */
function useBackendUp(): boolean {
  const [up, setUp] = useState(true)
  useEffect(() => {
    let alive = true
    const check = () =>
      api
        .health()
        .then(() => alive && setUp(true))
        .catch(() => alive && setUp(false))
    check()
    const timer = setInterval(check, 15000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])
  return up
}

export function Layout() {
  const [theme, setTheme] = useTheme()
  const up = useBackendUp()
  const next: Theme = theme === 'system' ? 'dark' : theme === 'dark' ? 'light' : 'system'
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand" aria-label="AMP Triage home">
            {/* The project's own figure: a helical wheel. Looking down the axis of a helix,
                each residue sits 100 degrees after the one before it. */}
            <svg width="30" height="30" viewBox="0 0 28 28" aria-hidden>
              <circle cx="14" cy="14" r="11" fill="none" stroke="var(--accent-line)" strokeWidth="1.2" />
              <path d="M14 3.5 24.3 15.8 10.4 23.9 4.9 8.8" fill="none" stroke="var(--accent-line)"
                strokeWidth="1.3" strokeLinejoin="round" />
              <circle cx="14" cy="3.5" r="2.9" fill="var(--accent)" />
              <circle cx="24.3" cy="15.8" r="2.9" fill="var(--accent)" />
              <circle cx="10.4" cy="23.9" r="2.9" fill="var(--accent)" />
              <circle cx="4.9" cy="8.8" r="2.9" fill="var(--accent)" />
            </svg>
            <span className="brand-name">AMP Triage</span>
          </NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Runs</NavLink>
            <NavLink to="/new">New run</NavLink>
            <NavLink to="/about">About</NavLink>
          </nav>
          <button className="quiet" onClick={() => setTheme(next)}
            title={`Theme: ${theme}. Click for ${next}.`}>
            {theme === 'dark' ? 'Dark' : theme === 'light' ? 'Light' : 'Auto'}
          </button>
        </div>
      </header>
      {!up && (
        <div className="banner" role="alert">
          Cannot reach the backend. Start it with{' '}
          <code>uvicorn amp_triage.api.main:app --port 8000</code>
        </div>
      )}
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
