import { Link, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { AboutPage } from './pages/AboutPage'
import { CandidatePage } from './pages/CandidatePage'
import { NewRunPage } from './pages/NewRunPage'
import { RunPage } from './pages/RunPage'
import { RunsPage } from './pages/RunsPage'

function NotFound() {
  return (
    <div className="card empty">
      <h1>Page not found</h1>
      <p style={{ margin: '8px 0 16px' }}>That address does not exist.</p>
      <Link to="/" className="button primary">Back to the runs</Link>
    </div>
  )
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<RunsPage />} />
        <Route path="new" element={<NewRunPage />} />
        <Route path="runs/:id" element={<RunPage />} />
        <Route path="runs/:id/candidate" element={<CandidatePage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
