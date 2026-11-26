import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'
import { App } from '../App'
import { ApiError, api } from '../api/client'
import type { Info } from '../api/types'
import { detail, proteinDetail, proteins, resultsPage, rows3, run } from '../test/fixtures'
import { AboutPage } from './AboutPage'
import { CandidatePage } from './CandidatePage'
import { NewRunPage, parseAccessions } from './NewRunPage'
import { RunPage } from './RunPage'
import { RunsPage } from './RunsPage'

const RUN = 'abc123def456'

function Where() {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}

function at(path: string, routePath: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={<>{element}<Where /></>} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok' })
})
afterEach(() => vi.restoreAllMocks())

// ---- New run ----------------------------------------------------------------------------

describe('parseAccessions', () => {
  it('splits on commas, spaces and new lines, upper-cases and removes repeats', () => {
    expect(parseAccessions('p69905, P02788\nP69905;  q9y6k9-2')).toEqual({
      valid: ['P69905', 'P02788', 'Q9Y6K9-2'],
      invalid: [],
    })
  })

  it('reports tokens that are not accessions', () => {
    expect(parseAccessions('P69905 hello 12345 P0278 nonsense').invalid).toEqual(['hello', '12345', 'P0278', 'nonsense'])
    expect(parseAccessions('   ')).toEqual({ valid: [], invalid: [] })
  })
})

describe('NewRunPage', () => {
  const start = () => at('/new', '/new', <NewRunPage />)

  it('cannot start until there is something valid to scan', async () => {
    start()
    const submit = screen.getByRole('button', { name: 'Start run' })
    expect(submit).toBeDisabled()
    expect(screen.getByText('Enter at least one accession.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Accessions/), { target: { value: 'P69905, nonsense' } })
    expect(submit).toBeDisabled()
    expect(screen.getByText(/Not a UniProt accession: nonsense/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Accessions/), { target: { value: 'P69905' } })
    expect(submit).toBeEnabled()
  })

  it('starts a run from accessions and opens it', async () => {
    const createRun = vi.spyOn(api, 'createRun').mockResolvedValue({ id: 'newrun', status_url: '' })
    start()
    await userEvent.click(screen.getByRole('button', { name: 'Use an example' }))
    await userEvent.click(screen.getByRole('button', { name: 'Start run' }))
    expect(createRun).toHaveBeenCalledWith({
      source: { type: 'accessions', accessions: ['P69905', 'P02788', 'P59665', 'P06881'] },
      options: { top_n: 200, prevalence: 0.001 },
      label: undefined,
    })
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/runs/newrun'))
  })

  it('sends pasted FASTA and the chosen options', async () => {
    const createRun = vi.spyOn(api, 'createRun').mockResolvedValue({ id: 'r2', status_url: '' })
    start()
    await userEvent.click(screen.getByRole('tab', { name: 'Paste FASTA' }))
    const box = screen.getByLabelText(/Proteins in FASTA format/)
    fireEvent.change(box, { target: { value: 'MKTAYIAKQR' } })
    expect(screen.getByText(/starts each protein with a line beginning/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start run' })).toBeDisabled()
    fireEvent.change(box, { target: { value: '>p1 test\nMKTAYIAKQRQISFVKSHFSRQ\n>p2\nMKTAYIAKQRQISFVKSHFSRQ' } })
    expect(screen.getByText(/2 protein\(s\) found/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: '  My proteins ' } })
    fireEvent.change(screen.getByLabelText(/Candidates to keep/), { target: { value: '50' } })
    fireEvent.change(screen.getByLabelText(/Assumed rarity/), { target: { value: '0.0001' } })
    await userEvent.click(screen.getByRole('button', { name: 'Start run' }))
    const body = createRun.mock.calls[0][0]
    expect(body.source).toEqual({ type: 'fasta', text: expect.stringContaining('>p1 test') })
    expect(body.options).toEqual({ top_n: 50, prevalence: 0.0001 })
    expect(body.label).toBe('My proteins')
  })

  it('searches organisms, picks one and asks for a sample', async () => {
    vi.spyOn(api, 'organisms').mockResolvedValue([
      { taxon_id: 83333, name: 'Escherichia coli (strain K12)', reviewed_proteins: 4531 },
      { taxon_id: 562, name: 'Escherichia coli', reviewed_proteins: 745 },
    ])
    const createRun = vi.spyOn(api, 'createRun').mockResolvedValue({ id: 'r3', status_url: '' })
    start()
    await userEvent.click(screen.getByRole('tab', { name: 'Organism' }))
    expect(screen.getByRole('button', { name: 'Start run' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Search an organism/), { target: { value: 'coli' } })
    const choice = await screen.findByRole('radio', { name: /Escherichia coli \(strain K12\)/ }, { timeout: 3000 })
    expect(screen.getByText(/4,531 proteins · taxon 83333/)).toBeInTheDocument()
    await userEvent.click(choice)
    fireEvent.change(screen.getByLabelText(/How many proteins to scan/), { target: { value: '25' } })
    await userEvent.click(screen.getByRole('button', { name: 'Start run' }))
    expect(createRun.mock.calls[0][0].source).toEqual({ type: 'organism', taxon_id: 83333, max_proteins: 25 })
  })

  it('shows the backend message when the run is refused and lets you try again', async () => {
    vi.spyOn(api, 'createRun').mockRejectedValue(new ApiError(422, '60,000 residues; the limit is 50,000.'))
    start()
    fireEvent.change(screen.getByLabelText(/Accessions/), { target: { value: 'P69905' } })
    await userEvent.click(screen.getByRole('button', { name: 'Start run' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('60,000 residues; the limit is 50,000.')
    expect(screen.getByRole('button', { name: 'Start run' })).toBeEnabled()
  })
})

// ---- Runs list --------------------------------------------------------------------------

describe('RunsPage', () => {
  function mockRuns(list: ReturnType<typeof run>[]) {
    vi.spyOn(api, 'listRuns').mockResolvedValue(list)
    vi.spyOn(api, 'proteins').mockResolvedValue(proteins)
    vi.spyOn(api, 'protein').mockResolvedValue(proteinDetail)
  }

  it('shows every run as a card carrying its status and figures', async () => {
    mockRuns([
      run({ label: 'Human blood proteins' }),
      run({ id: 'b'.repeat(12), label: 'E. coli sample', kind: 'organism', status: 'running', progress: 0.4 }),
      run({ id: 'c'.repeat(12), label: 'Broken one', status: 'failed', error: 'UniProt timed out.' }),
    ])
    at('/', '/', <RunsPage />)
    expect(await screen.findByRole('link', { name: 'Human blood proteins' })).toHaveAttribute(
      'href',
      `/runs/${RUN}`,
    )
    expect(screen.getAllByRole('article')).toHaveLength(3)
    expect(screen.getByText(/Organism sample/)).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('UniProt timed out.')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'E. coli sample progress' })).toHaveAttribute(
      'aria-valuenow',
      '40',
    )
  })

  it('totals every run in the hero figures', async () => {
    mockRuns([run(), run({ id: 'b'.repeat(12) })])
    at('/', '/', <RunsPage />)
    expect(await screen.findByText('Windows scored')).toBeInTheDocument()
    // each fixture run scored 106,812 windows over 12 proteins
    expect(screen.getByText('213,624')).toBeInTheDocument()
    expect(screen.getByText('24')).toBeInTheDocument()
    // candidates come from the per-run protein lists: 35 + 9 in each of the two runs
    expect(await screen.findByText('88')).toBeInTheDocument()
  })

  it('invites you to start the first run when there are none', async () => {
    vi.spyOn(api, 'listRuns').mockResolvedValue([])
    at('/', '/', <RunsPage />)
    expect(await screen.findByText('No runs yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start the first run' })).toHaveAttribute('href', '/new')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('deletes a run after confirmation and reloads', async () => {
    mockRuns([run({ label: 'Old run' })])
    const del = vi.spyOn(api, 'deleteRun').mockResolvedValue(undefined)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true)
    at('/', '/', <RunsPage />)
    const button = await screen.findByRole('button', { name: 'Delete run Old run' })
    await userEvent.click(button)
    expect(del).not.toHaveBeenCalled() // cancelled
    await userEvent.click(button)
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(del).toHaveBeenCalledWith(RUN)
    await waitFor(() => expect(api.listRuns).toHaveBeenCalledTimes(2))
  })

  it('does not offer to delete a run that is still going', async () => {
    mockRuns([run({ label: 'Busy', status: 'running', progress: 0.2 })])
    at('/', '/', <RunsPage />)
    expect(await screen.findByRole('button', { name: 'Delete run Busy' })).toBeDisabled()
  })

  it('says so when the runs cannot be loaded', async () => {
    vi.spyOn(api, 'listRuns').mockRejectedValue(
      new ApiError(0, 'Cannot reach the backend. Is it running on port 8000?'),
    )
    at('/', '/', <RunsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the backend')
  })
})

// ---- A run --------------------------------------------------------------------------------

describe('RunPage', () => {
  function mockDone(total = rows3.length) {
    vi.spyOn(api, 'getRun').mockResolvedValue(run({ notes: ['A random sample of 12 of 4,531 proteins was scanned.'] }))
    vi.spyOn(api, 'proteins').mockResolvedValue(proteins)
    const results = vi.spyOn(api, 'results').mockResolvedValue(resultsPage(rows3, { total }))
    const protein = vi.spyOn(api, 'protein').mockResolvedValue(proteinDetail)
    return { results, protein }
  }
  const open = (search = '') => at(`/runs/${RUN}${search}`, 'runs/:id', <RunPage />)

  it('shows progress while the run is working and the results when it is done', async () => {
    vi.spyOn(api, 'getRun')
      .mockResolvedValueOnce(run({ status: 'running', progress: 0.3, message: 'scanned 800 of 2,820 residues' }))
      .mockResolvedValue(run())
    vi.spyOn(api, 'proteins').mockResolvedValue(proteins)
    vi.spyOn(api, 'results').mockResolvedValue(resultsPage(rows3))
    open()
    expect(await screen.findByText('Scanning')).toBeInTheDocument()
    expect(screen.getByText('30%')).toBeInTheDocument()
    expect(screen.getByText(/scanned 800 of 2,820 residues/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Run progress' })).toHaveAttribute('aria-valuenow', '30')
    expect(await screen.findByRole('link', { name: 'RRARVVWC' }, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.queryByText('Scanning')).not.toBeInTheDocument()
  }, 10000)

  it('shows the summary, the notes and the ranked list of a finished run', async () => {
    mockDone()
    open()
    expect(await screen.findByRole('link', { name: 'RRARVVWC' })).toBeInTheDocument()
    const summary = screen.getByRole('group', { name: 'Run summary' })
    for (const label of ['Windows scored', 'Proteins', 'Residues', 'Candidates kept', 'Scan time'])
      expect(within(summary).getByText(label)).toBeInTheDocument()
    // each figure also carries its final value for screen readers, whatever the count-up is on
    expect(summary).toHaveTextContent('106,812')
    expect(summary).toHaveTextContent('2,820')
    expect(summary).toHaveTextContent('12 s')
    expect(screen.getByText(/A random sample of 12 of 4,531 proteins/)).toBeInTheDocument()
    expect(screen.getByText('Showing 1–3 of 3')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Export CSV' }).getAttribute('href')).toContain(`/api/runs/${RUN}/results.csv?`)
  })

  it('re-ranks when a weight moves, and keeps the view in the address', async () => {
    const { results } = mockDone()
    open()
    await screen.findByRole('link', { name: 'RRARVVWC' })
    fireEvent.change(screen.getByLabelText(/Safety weight/), { target: { value: '2' } })
    await waitFor(() =>
      expect(results).toHaveBeenCalledWith(
        RUN,
        expect.objectContaining({ safetyWeight: 2 }),
        { limit: 25, offset: 0 },
        expect.anything(),
      ),
    )
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('sw=2'))
    expect(screen.getByRole('link', { name: 'Export CSV' }).getAttribute('href')).toContain('safety_weight=2')
    fireEvent.click(screen.getByRole('button', { name: /Reset/ }))
    await waitFor(() => expect(screen.getByTestId('where').textContent).not.toContain('sw='))
  })

  it('opens with the view that is in the address', async () => {
    const { results } = mockDone()
    open('?sw=2&hk=1&tab=chart')
    expect(await screen.findByText('Novel (1)')).toBeInTheDocument() // the scatter plot's legend
    expect(results).toHaveBeenCalledWith(
      RUN,
      expect.objectContaining({ safetyWeight: 2, hideKnown: true }),
      { limit: 1000, offset: 0 },
      expect.anything(),
    )
    expect(screen.getByLabelText(/Safety weight/)).toHaveValue('2')
    expect(screen.getByLabelText('Hide known AMPs')).toBeChecked()
  })

  it('pages through the candidates', async () => {
    const { results } = mockDone(60)
    open()
    expect(await screen.findByText('Showing 1–25 of 60')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(results).toHaveBeenCalledWith(RUN, expect.anything(), { limit: 25, offset: 25 }, expect.anything()),
    )
    expect(await screen.findByText('Showing 26–50 of 60')).toBeInTheDocument()
  })

  it('has a protein view that starts with the protein that has most candidates', async () => {
    const { protein } = mockDone()
    open()
    await screen.findByRole('link', { name: 'RRARVVWC' })
    await userEvent.click(screen.getByRole('tab', { name: 'Proteins' }))
    expect(await screen.findByRole('link', { name: /Rank 1, residues 360 to 367/ })).toBeInTheDocument()
    expect(protein).toHaveBeenLastCalledWith(RUN, 'P02788', expect.anything(), expect.anything())
    await userEvent.click(screen.getByRole('button', { name: /P68871/ }))
    await waitFor(() =>
      expect(protein).toHaveBeenLastCalledWith(RUN, 'P68871', expect.anything(), expect.anything()),
    )
    expect(screen.getByTestId('where')).toHaveTextContent('tab=proteins')
  })

  it('says so when the filters leave nothing', async () => {
    vi.spyOn(api, 'getRun').mockResolvedValue(run())
    vi.spyOn(api, 'proteins').mockResolvedValue(proteins)
    vi.spyOn(api, 'results').mockResolvedValue(resultsPage([], { total: 0 }))
    open('?mh=0.1')
    expect(await screen.findByText('No candidate matches these filters.')).toBeInTheDocument()
    expect(screen.getByText('No candidates')).toBeInTheDocument()
  })

  it('shows why a run failed', async () => {
    vi.spyOn(api, 'getRun').mockResolvedValue(
      run({ status: 'failed', error: 'UniProt answered with HTTP 503.', progress: 0.1 }),
    )
    open()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This run failed')
    expect(alert).toHaveTextContent('UniProt answered with HTTP 503.')
  })

  it('says so when the run does not exist', async () => {
    vi.spyOn(api, 'getRun').mockRejectedValue(new ApiError(404, "No run with id 'abc123def456'."))
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load this run')
    expect(screen.getByRole('alert')).toHaveTextContent("No run with id 'abc123def456'.")
  })
})

// ---- A candidate ------------------------------------------------------------------------------

describe('CandidatePage', () => {
  const open = () =>
    at(`/runs/${RUN}/candidate?accession=P02788&start=360&end=367&p=0.0001`, 'runs/:id/candidate', <CandidatePage />)

  it('shows the peptide, its scores, properties, alignment and notes', async () => {
    const candidate = vi.spyOn(api, 'candidate').mockResolvedValue(detail())
    open()
    expect(await screen.findByRole('heading', { name: 'Peptide RRARVVWC' })).toBeInTheDocument()
    expect(candidate).toHaveBeenCalledWith(RUN, 'P02788', 360, 367, 0.0001, expect.anything())
    expect(screen.getByText('Rank 1')).toBeInTheDocument()
    expect(screen.getByText(/Residues 360–367 of P02788 \(Lactotransferrin\), 8 residues/)).toBeInTheDocument()
    expect(screen.getByText('0.44')).toBeInTheDocument()
    expect(screen.getByText(/1 in 10,000 windows were real AMPs/)).toBeInTheDocument()
    expect(screen.getByText('Net charge')).toBeInTheDocument()
    expect(screen.getByText('2.85')).toBeInTheDocument()
    expect(screen.getByText('64%')).toBeInTheDocument() // closest similarity
    expect(screen.getByRole('img', { name: /57% of columns identical/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy raw' })).toBeInTheDocument()
    expect(screen.getByText(/Not clearly similar to any known AMP in the reference of 17,492/)).toBeInTheDocument()
  })

  it('marks the peptide inside its surroundings', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(detail())
    const { container } = open()
    await screen.findByRole('heading', { name: 'Peptide RRARVVWC' })
    const marked = [...container.querySelectorAll('.seq-context .in-peptide')]
      .map((e) => e.textContent)
      .join('')
    expect(marked).toBe('RRARVVWC')
    const context = container.querySelector('.seq-context')!
    expect(context.textContent).toContain('LRKSEEEVAA' + 'RRARVVWC' + 'AVGEQELRKC')
  })

  it('copes with a candidate that has no alignment', async () => {
    vi.spyOn(api, 'candidate').mockResolvedValue(detail({ alignment: null }))
    open()
    expect(await screen.findByText('No alignment is available for this candidate.')).toBeInTheDocument()
  })

  it('shows the error when the candidate cannot be loaded', async () => {
    vi.spyOn(api, 'candidate').mockRejectedValue(new ApiError(404, 'No such candidate in this run.'))
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('No such candidate in this run.')
    expect(screen.getByRole('button', { name: '← Back' })).toBeInTheDocument()
  })
})

// ---- About and the shell ---------------------------------------------------------------------

const info: Info = {
  default_prevalence: 0.001,
  limits: { max_residues: 100000, max_proteins: 5000, scan_speed_windows_per_second: 23000 },
  rank_formula: 'activity ^ a  x  (1 - hemolysis risk) ^ s  x  novelty factor ^ n',
  novelty_labels: {
    known: 'identical to / part of a known AMP',
    related: 'similar to a known AMP, above chance',
    novel: 'not clearly similar to any known AMP',
  },
  activity_test: {
    all: { roc_auc: 0.934, pr_auc: 0.598, 'recall@fpr=0.001': 0.419, 'recall@fpr=0.0001': 0.212 },
    natural: { roc_auc: 0.924, pr_auc: 0.475, 'recall@fpr=0.001': 0.341, 'recall@fpr=0.0001': 0.129 },
    synthetic: { roc_auc: 0.951, pr_auc: 0.605, 'recall@fpr=0.001': 0.555, 'recall@fpr=0.0001': 0.358 },
  },
  hemolysis_test: { 'ROC AUC': { value: 0.75, ci95: [0.674, 0.816] } },
  caveat: 'The activity number assumes that 1 in 1,000 of all windows are real AMPs, which is a guess.',
}

describe('AboutPage', () => {
  it('explains the pipeline and reports the test results from the backend', async () => {
    vi.spyOn(api, 'info').mockResolvedValue(info)
    at('/about', '/about', <AboutPage />)
    expect(await screen.findByText('How well does it work?')).toBeInTheDocument()
    const natural = screen.getByRole('row', { name: /natural/i })
    expect(within(natural).getByText('0.924')).toBeInTheDocument()
    expect(within(natural).getByText('34%')).toBeInTheDocument()
    expect(within(natural).getByText('13%')).toBeInTheDocument()
    expect(screen.getByText('0.75')).toBeInTheDocument() // hemolysis ROC AUC
    // the formula is set with real superscripts now, so it spans several elements
    expect(document.querySelector('.formula')).toHaveTextContent(
      'activitya×(1 − hemolysis risk)s×noveltyn', // the exponents are <sup>, so no spaces
    )
    for (const step of ['Scan', 'Merge', 'Check', 'Rank'])
      expect(screen.getByText(step)).toBeInTheDocument()
    expect(screen.getByText(info.caveat)).toBeInTheDocument()
    expect(screen.getByText(/100,000 residues and/)).toBeInTheDocument()
    expect(screen.getByText(/Half of all real AMPs are novel/)).toBeInTheDocument()
  })

  it('shows an error when the model details cannot be loaded', async () => {
    vi.spyOn(api, 'info').mockRejectedValue(new ApiError(0, 'Cannot reach the backend. Is it running on port 8000?'))
    at('/about', '/about', <AboutPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the model details')
  })
})

describe('the app shell', () => {
  const shell = (path: string) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    )

  it('has a navigation and a page for unknown addresses', () => {
    vi.spyOn(api, 'listRuns').mockResolvedValue([])
    shell('/nowhere')
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
    expect(screen.getByText('Page not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the runs' })).toHaveAttribute('href', '/')
  })

  it('marks the page you are on in the navigation', async () => {
    vi.spyOn(api, 'listRuns').mockResolvedValue([])
    shell('/')
    expect(await screen.findByRole('link', { name: 'Runs', current: 'page' })).toBeInTheDocument()
    const nav = within(screen.getByRole('navigation', { name: 'Main' }))
    expect(nav.getByRole('link', { name: 'New run' })).not.toHaveAttribute('aria-current')
  })

  it('warns when the backend is not running', async () => {
    vi.spyOn(api, 'health').mockRejectedValue(new ApiError(0, 'down'))
    vi.spyOn(api, 'listRuns').mockResolvedValue([])
    shell('/')
    expect(await screen.findByText(/Cannot reach the backend/, { selector: '.banner' })).toBeInTheDocument()
    expect(screen.getByText('uvicorn amp_triage.api.main:app --port 8000')).toBeInTheDocument()
  })

  it('draws the molecular lattice behind the page, out of the way of the pointer', async () => {
    vi.spyOn(api, 'listRuns').mockResolvedValue([])
    const { container } = shell('/')
    await screen.findByRole('heading', { name: 'Runs' })
    const lattice = container.querySelector('canvas.lattice')
    expect(lattice).toBeInTheDocument()
    expect(lattice).toHaveAttribute('aria-hidden')
  })
})
