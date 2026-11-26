import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { Lattice } from './Lattice'

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

/** Four residues of a peptide chain, in the colours the whole interface is built from. */
function Mark() {
  const beads: [number, number, string][] = [
    [5, 18, 'var(--res-basic)'],
    [11, 9.5, 'var(--res-oily)'],
    [18, 17, 'var(--res-acidic)'],
    [24, 8.5, 'var(--res-oily)'],
  ]
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden>
      <path
        d="M5 18 11 9.5 18 17 24 8.5"
        fill="none"
        stroke="var(--res-other)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.8"
      />
      {beads.map(([cx, cy, fill]) => (
        <circle key={cx} cx={cx} cy={cy} r="3.4" fill={fill} stroke="var(--bg-base)" strokeWidth="1.4" />
      ))}
    </svg>
  )
}

export function Layout() {
  const up = useBackendUp()
  const location = useLocation()

  return (
    <>
      <Lattice />
      <div className="shell">
        <header className="topbar">
          <div className="topbar-inner">
            <NavLink to="/" className="brand" aria-label="AMP Triage home">
              <Mark />
              <span className="brand-name">AMP Triage</span>
            </NavLink>
            <nav className="nav" aria-label="Main">
              <NavLink to="/" end>
                Runs
              </NavLink>
              <NavLink to="/new">New run</NavLink>
              <NavLink to="/about">About</NavLink>
            </nav>
          </div>
        </header>
        {!up && (
          <div className="banner" role="alert">
            Cannot reach the backend. Start it with{' '}
            <code>uvicorn amp_triage.api.main:app --port 8000</code>
          </div>
        )}
        <main className="main">
          <div className="route" key={location.pathname}>
            <Outlet />
          </div>
        </main>
      </div>
    </>
  )
}
