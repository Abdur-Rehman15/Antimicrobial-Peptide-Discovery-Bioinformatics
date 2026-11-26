import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, vi } from 'vitest'
import { candidate, detail, proteinDetail, proteins, rows3 } from '../test/fixtures'
import { DEFAULT_VIEW } from '../lib/view'
import type { View } from '../api/types'
import { BandChip, NoveltyChip, StatusChip } from './Chips'
import { CompositionChart } from './CompositionChart'
import { HelicalWheel } from './HelicalWheel'
import { ProteinMap, assignLanes, ridgeMax, tickStep } from './ProteinMap'
import { ResultsControls } from './ResultsControls'
import { ResultsTable } from './ResultsTable'
import { ScatterPlot, logRange } from './ScatterPlot'
import { AlignmentView } from './AlignmentView'
import { PropertyBar } from './PropertyBar'
import { Sequence, SequenceContext, SequenceHero, SequenceKey } from './Sequence'

function Where() {
  const { pathname, search } = useLocation()
  return <p data-testid="where">{pathname + search}</p>
}

function inRouter(node: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={['/start']}>
      <Routes>
        <Route path="/start" element={node} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('chips never rely on colour alone', () => {
  it('writes the word next to every colour', () => {
    render(
      <>
        <NoveltyChip value="novel" />
        <NoveltyChip value="related" />
        <NoveltyChip value="known" />
        <BandChip band="low" />
        <BandChip band="medium" />
        <BandChip band="high" risk={0.8} />
        <StatusChip state="running" />
      </>,
    )
    for (const word of ['Novel', 'Related', 'Known', 'Low risk', 'Medium risk', 'High risk', 'Running']) {
      expect(screen.getByText(word)).toBeInTheDocument()
    }
    expect(screen.getByText('High risk').closest('.chip')).toHaveAttribute(
      'title',
      expect.stringContaining('0.80'),
    )
  })
})

describe('ResultsTable', () => {
  it('shows every candidate with its chips and links to the detail page', () => {
    inRouter(<ResultsTable runId="r1" rows={rows3} prevalence={0.001} />)
    expect(screen.getAllByRole('row')).toHaveLength(4) // header + 3
    expect(screen.getByText('Low risk')).toBeInTheDocument()
    expect(screen.getByText('Medium risk')).toBeInTheDocument()
    expect(screen.getByText('High risk')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'RRARVVWC' })
    expect(link).toHaveAttribute('href', expect.stringContaining('/runs/r1/candidate?accession=P02788&start=360&end=367'))
    expect(link.getAttribute('href')).toContain('p=0.001')
  })

  it('keeps a long peptide whole, and lets the column clip it', () => {
    inRouter(<ResultsTable runId="r1" rows={rows3} prevalence={0.001} />)
    const long = screen.getByTitle('GSRKNMACYCRIPACIAGERRYGTCIYQGRLWAFCC')
    // the whole sequence is in the page, so the link's name matches what is on screen
    expect(long).toHaveTextContent('GSRKNMACYCRIPACIAGERRYGTCIYQGRLWAFCC')
    expect(long).toHaveClass('seq')
    expect(
      screen.getByRole('link', { name: 'GSRKNMACYCRIPACIAGERRYGTCIYQGRLWAFCC' }),
    ).toBeInTheDocument()
  })

  it('opens the candidate when a row is clicked', async () => {
    inRouter(<ResultsTable runId="r1" rows={rows3} prevalence={0.001} />)
    await userEvent.click(screen.getByRole('link', { name: 'GKKVLGAFSDGLA' }).closest('[role="row"]')!)
    expect(screen.getByTestId('where').textContent).toContain('accession=P68871&start=65&end=77')
  })

  it('says so when nothing matches, and dims the table while reloading', () => {
    const { unmount } = inRouter(<ResultsTable runId="r1" rows={[]} prevalence={0.001} />)
    expect(screen.getByText(/No candidate matches/)).toBeInTheDocument()
    unmount()
    const { container } = inRouter(<ResultsTable runId="r1" rows={rows3} prevalence={0.001} loading />)
    expect(container.querySelector('.table-wrap')).toHaveClass('dim')
    expect(container.querySelector('.table-wrap')).toHaveAttribute('aria-busy', 'true')
  })
})

describe('ResultsControls', () => {
  function setup(view: View = DEFAULT_VIEW, proteinList = proteins) {
    const onChange = vi.fn()
    render(<ResultsControls view={view} onChange={onChange} proteins={proteinList} />)
    return onChange
  }

  it('changes the three weights', () => {
    const onChange = setup()
    fireEvent.change(screen.getByLabelText(/Activity weight/), { target: { value: '2' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, activityWeight: 2 })
    fireEvent.change(screen.getByLabelText(/Safety weight/), { target: { value: '0' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, safetyWeight: 0 })
    fireEvent.change(screen.getByLabelText(/Novelty weight/), { target: { value: '1.5' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, noveltyWeight: 1.5 })
  })

  it('sets the assumed rarity on a log scale and shows it in words', () => {
    const onChange = setup()
    expect(screen.getByText('1 in 1,000')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Assumed rarity/), { target: { value: '-4' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, prevalence: 0.0001 })
  })

  it('hides known AMPs and then disables the "Known" box', () => {
    const onChange = setup()
    fireEvent.click(screen.getByLabelText('Hide known AMPs'))
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, hideKnown: true })
    onChange.mockClear()
    render(<ResultsControls view={{ ...DEFAULT_VIEW, hideKnown: true }} onChange={onChange} proteins={null} />)
    expect(screen.getAllByLabelText('Known')[1]).toBeDisabled()
  })

  it('unchecking one class from "all" lists the other two', () => {
    const onChange = setup()
    fireEvent.click(screen.getByLabelText('Related'))
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, novelty: ['novel', 'known'] })
  })

  it('switching the third class back on returns to "all", and the last one cannot be switched off', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <ResultsControls view={{ ...DEFAULT_VIEW, novelty: ['novel', 'related'] }} onChange={onChange} proteins={null} />,
    )
    fireEvent.click(screen.getByLabelText('Known'))
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, novelty: [] })
    onChange.mockClear()
    rerender(<ResultsControls view={{ ...DEFAULT_VIEW, novelty: ['novel'] }} onChange={onChange} proteins={null} />)
    fireEvent.click(screen.getByLabelText('Novel'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('filters by hemolysis band, length and protein', () => {
    const onChange = setup()
    fireEvent.change(screen.getByLabelText('Hemolysis risk'), { target: { value: 'low' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, maxHemolysis: 0.33 })
    fireEvent.change(screen.getByLabelText('Hemolysis risk'), { target: { value: 'medium' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, maxHemolysis: 0.66 })
    fireEvent.change(screen.getByLabelText('Hemolysis risk'), { target: { value: 'any' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, maxHemolysis: null })
    fireEvent.change(screen.getByLabelText('Min length'), { target: { value: '12' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, minLength: 12 })
    fireEvent.change(screen.getByLabelText('Max length'), { target: { value: '30' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, maxLength: 30 })
    fireEvent.change(screen.getByLabelText('Protein'), { target: { value: 'P68871' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, accession: 'P68871' })
  })

  it('clearing a length box removes that limit', () => {
    const onChange = setup({ ...DEFAULT_VIEW, minLength: 12, maxLength: 30 })
    fireEvent.change(screen.getByLabelText('Max length'), { target: { value: '' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_VIEW, minLength: 12, maxLength: null })
  })

  it('only offers a protein filter when there is more than one protein', () => {
    setup(DEFAULT_VIEW, [proteins[0]])
    expect(screen.queryByLabelText('Protein')).not.toBeInTheDocument()
  })

  it('resets to the default view and counts what was changed', () => {
    const changed = { ...DEFAULT_VIEW, safetyWeight: 2, hideKnown: true, minLength: 10 }
    const onChange = setup(changed)
    const reset = screen.getByRole('button', { name: 'Reset (3)' })
    fireEvent.click(reset)
    expect(onChange).toHaveBeenCalledWith(DEFAULT_VIEW)
  })

  it('has nothing to reset on the default view', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled()
  })
})

describe('ScatterPlot', () => {
  const rect = { left: 0, top: 0, width: 760, height: 420, right: 760, bottom: 420, x: 0, y: 0, toJSON: () => ({}) }

  it('chooses whole decades for the logarithmic activity axis', () => {
    expect(logRange([0.44, 0.02, 0.0013])).toEqual({ minExp: -3, maxExp: 0 })
    expect(logRange([0.04, 0.03])).toEqual({ minExp: -2, maxExp: -1 })
    expect(logRange([0.05])).toEqual({ minExp: -2, maxExp: -1 }) // never a zero-height axis
    expect(logRange([1e-9, 0.5])).toEqual({ minExp: -4, maxExp: 0 }) // floored at 1e-4
    expect(logRange([])).toEqual({ minExp: -3, maxExp: 0 })
  })

  it('draws one dot per candidate and counts the classes in the legend', () => {
    render(<ScatterPlot candidates={rows3} onSelect={() => {}} />)
    expect(screen.getAllByTestId('point')).toHaveLength(3)
    expect(screen.getByText('Novel (1)')).toBeInTheDocument()
    expect(screen.getByText('Related (1)')).toBeInTheDocument()
    expect(screen.getByText('Known (1)')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName(/3 candidates/)
  })

  it('shows the nearest candidate under the pointer, not only the one exactly under it', () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(rect as DOMRect)
    const { container } = render(<ScatterPlot candidates={rows3} onSelect={() => {}} />)
    const first = screen.getAllByTestId('point')[0]
    const cx = Number(first.getAttribute('cx'))
    const cy = Number(first.getAttribute('cy'))
    const chart = container.querySelector('.chart')!
    fireEvent.pointerMove(chart, { clientX: cx + 12, clientY: cy - 9 }) // 15 px away: still a hit
    const tip = screen.getByRole('tooltip')
    expect(within(tip).getByText(/#1 · P02788 360–367/)).toBeInTheDocument()
    expect(within(tip).getByText('RRARVVWC')).toBeInTheDocument()
    expect(within(tip).getByText('0.44')).toBeInTheDocument()
    expect(within(tip).getByText('0.09 (low)')).toBeInTheDocument()
    fireEvent.pointerMove(chart, { clientX: 2, clientY: 2 }) // far from every dot
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    fireEvent.pointerLeave(chart)
  })

  it('selects the candidate that was clicked', () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(rect as DOMRect)
    const onSelect = vi.fn()
    const { container } = render(<ScatterPlot candidates={rows3} onSelect={onSelect} />)
    const third = screen.getAllByTestId('point')[2]
    fireEvent.click(container.querySelector('.chart')!, {
      clientX: Number(third.getAttribute('cx')),
      clientY: Number(third.getAttribute('cy')),
    })
    expect(onSelect).toHaveBeenCalledWith(rows3[2])
    onSelect.mockClear()
    fireEvent.click(container.querySelector('.chart')!, { clientX: 1, clientY: 1 })
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('labels only the top three ranks', () => {
    const many = Array.from({ length: 6 }, (_, i) =>
      candidate({ rank: i + 1, accession: `P${i}`, hemolysis_risk: i / 10, activity: 0.5 / (i + 1) }),
    )
    const { container } = render(<ScatterPlot candidates={many} onSelect={() => {}} />)
    const labels = [...container.querySelectorAll('svg > text')].map((t) => t.textContent)
    for (const rank of ['1', '2', '3']) expect(labels).toContain(rank)
    for (const rank of ['4', '5', '6']) expect(labels).not.toContain(rank)
  })
})

describe('ProteinMap helpers', () => {
  it('puts overlapping regions on different rows and touching ones on the same row', () => {
    expect(assignLanes([{ start: 1, end: 10 }, { start: 11, end: 20 }])).toEqual([0, 0])
    expect(assignLanes([{ start: 1, end: 10 }, { start: 5, end: 15 }])).toEqual([0, 1])
    expect(assignLanes([{ start: 1, end: 10 }, { start: 5, end: 15 }, { start: 12, end: 30 }])).toEqual([0, 1, 0])
    expect(assignLanes([])).toEqual([])
  })

  it('picks round tick steps', () => {
    expect(tickStep(40)).toBe(10)
    expect(tickStep(300)).toBe(50)
    expect(tickStep(710)).toBe(100)
    expect(tickStep(5000)).toBe(1000)
    expect(tickStep(100000)).toBe(2000)
  })
})

describe('ProteinMap', () => {
  it('draws every region as a link with a readable name', () => {
    inRouter(<ProteinMap protein={proteinDetail} runId="r1" prevalence={0.001} />)
    expect(screen.getByRole('link', { name: 'Rank 1, residues 360 to 367, Novel' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Rank 7, residues 362 to 380, Related' })).toBeInTheDocument()
    expect(screen.getByRole('group')).toHaveAccessibleName(/P02788, 710 residues, with 2 candidate regions/)
    const ys = screen.getAllByRole('link').map((g) => g.querySelector('rect')!.getAttribute('y'))
    expect(new Set(ys).size).toBe(2) // the two overlapping regions are on separate rows
  })

  it('opens the candidate on click and on Enter, and shows details on focus', async () => {
    const { unmount } = inRouter(<ProteinMap protein={proteinDetail} runId="r1" prevalence={0.001} />)
    const first = screen.getByRole('link', { name: /Rank 1,/ })
    fireEvent.focus(first)
    expect(screen.getByRole('tooltip')).toHaveTextContent('RRARVVWC')
    fireEvent.click(first)
    expect(screen.getByTestId('where').textContent).toContain('accession=P02788&start=360&end=367')
    unmount()
    inRouter(<ProteinMap protein={proteinDetail} runId="r1" prevalence={0.001} />)
    fireEvent.keyDown(screen.getByRole('link', { name: /Rank 7,/ }), { key: 'Enter' })
    expect(screen.getByTestId('where').textContent).toContain('start=362&end=380')
  })
})

describe('peptide figures', () => {
  it('draws the helical wheel with one disc per residue', () => {
    render(<HelicalWheel sequence="RRARVVWC" />)
    expect(screen.getByRole('img')).toHaveAccessibleName(/Helical wheel of RRARVVWC/)
    for (const letter of ['R', 'A', 'V', 'W', 'C']) expect(screen.getAllByText(letter).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/^Residue \d+: /)).toHaveLength(8)
    // the wheel is turned so the oily face meets the drawn membrane
    expect(screen.getByText('membrane')).toBeInTheDocument()
    expect(screen.getByText('water')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName(/oily face points at a membrane/)
    // the wheel speaks the same language as the sequence above it
    expect(screen.getByText('Basic (K, R)')).toBeInTheDocument()
    expect(screen.getByText('Oily (A C F I L M V W)')).toBeInTheDocument()
  })

  it('draws no membrane for a peptide with no oily side to point anywhere', () => {
    // 18 residues sit at 18 evenly spaced angles, so identical ones cancel exactly
    render(<HelicalWheel sequence={'A'.repeat(18)} />)
    expect(screen.queryByText('membrane')).not.toBeInTheDocument()
    expect(screen.getByText(/no oily side to speak of/)).toBeInTheDocument()
  })

  it('lists only the residue classes the peptide actually has', () => {
    render(<HelicalWheel sequence="KKRR" />)
    expect(screen.getByText('Basic (K, R)')).toBeInTheDocument()
    expect(screen.queryByText('Acidic (D, E)')).not.toBeInTheDocument()
    expect(screen.queryByText('Other')).not.toBeInTheDocument()
  })

  it('draws the composition with every amino acid and labels the tallest bar', () => {
    const composition = Object.fromEntries([...'ACDEFGHIKLMNPQRSTVWY'].map((a) => [a, a === 'R' ? 0.375 : 0.125 * Number(a === 'A')]))
    render(<CompositionChart composition={composition} />)
    expect(screen.getByRole('img')).toHaveAccessibleName(/most common is R at 38%/)
    expect(screen.getByText('38%')).toBeInTheDocument()
    for (const aa of 'ACDEFGHIKLMNPQRSTVWY') expect(screen.getAllByText(aa).length).toBeGreaterThan(0)
  })
})

describe('sequences carry their chemistry', () => {
  it('colours each residue by charge and shades the oily ones', () => {
    const { container } = render(<Sequence sequence="KRDEAG" />)
    const classes = [...container.querySelectorAll('.seq > span')].map((s) => s.className)
    expect(classes).toEqual([
      'res-basic', 'res-basic', 'res-acidic', 'res-acidic', 'res-oily', 'res-other',
    ])
    expect(container.querySelector('.seq')).toHaveTextContent('KRDEAG')
  })

  it('keeps the whole peptide in the tooltip when the shown text is shortened', () => {
    render(<Sequence sequence="KRDE…WFLL" title="KRDEAAAAAAAAAAAAWFLL" />)
    expect(screen.getByTitle('KRDEAAAAAAAAAAAAWFLL')).toBeInTheDocument()
  })

  it('makes the peptide the page heading and explains the colours once', () => {
    render(
      <>
        <SequenceHero sequence="RRARVVWC" />
        <SequenceKey />
      </>,
    )
    expect(screen.getByRole('heading', { name: 'Peptide RRARVVWC' })).toBeInTheDocument()
    for (const word of ['basic', 'acidic', 'oily']) {
      expect(screen.getByText(word)).toBeInTheDocument()
    }
  })

  it('marks the peptide inside its surroundings and shows where the protein was cut', () => {
    const { container } = render(
      <SequenceContext before="AAKL" peptide="KRWW" after="GGPE" truncatedStart truncatedEnd />,
    )
    const marked = [...container.querySelectorAll('.in-peptide')].map((e) => e.textContent).join('')
    expect(marked).toBe('KRWW')
    expect(container.querySelector('.seq-context')).toHaveTextContent('…AAKLKRWWGGPE…')
  })

  it('leaves out the ellipsis at a protein end', () => {
    const { container } = render(
      <SequenceContext
        before="MA"
        peptide="KRWW"
        after="GG"
        truncatedStart={false}
        truncatedEnd={false}
      />,
    )
    expect(container.querySelector('.seq-context')!.textContent).toBe('MAKRWWGG')
  })
})

describe('the protein ridge', () => {
  const rect = { left: 0, top: 0, width: 760, height: 300, right: 760, bottom: 300, x: 0, y: 0, toJSON: () => ({}) }
  const withRidge = {
    ...proteinDetail,
    length: 40,
    profile: [...Array(40)].map((_, i) => (i >= 18 && i < 26 ? 0.4 : 0.01)),
  }

  it('rounds the top of the activity axis to a readable number', () => {
    expect(ridgeMax(0.045)).toBe(0.05)
    expect(ridgeMax(0.4)).toBe(0.5)
    expect(ridgeMax(0.21)).toBe(0.25)
    expect(ridgeMax(0)).toBe(1)
  })

  it('draws the ridge and says what it is', () => {
    const { container } = inRouter(<ProteinMap protein={withRidge} runId="r1" prevalence={0.001} />)
    expect(container.querySelector('path[stroke="var(--accent)"]')).toBeInTheDocument()
    expect(screen.getByText(/best score of any window covering each residue/)).toBeInTheDocument()
    expect(screen.getByText(/highest 0.40 near residue 19/)).toBeInTheDocument()
  })

  it('reads out the residue under the pointer', () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(rect as DOMRect)
    const { container } = inRouter(<ProteinMap protein={withRidge} runId="r1" prevalence={0.001} />)
    fireEvent.pointerMove(container.querySelector('.chart')!, { clientX: 380, clientY: 40 })
    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent(/Residue \d+/)
    expect(tip).toHaveTextContent('Best window here')
    fireEvent.pointerLeave(container.querySelector('.chart')!)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('falls back to a plain bar for a run scanned before the ridge existed', () => {
    const { container } = inRouter(<ProteinMap protein={proteinDetail} runId="r1" prevalence={0.001} />)
    expect(container.querySelector('path[stroke="var(--accent)"]')).not.toBeInTheDocument()
    expect(screen.getByText(/Overlapping regions sit on separate rows/)).toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(2) // the candidates still draw
  })
})

describe('the alignment', () => {
  const alignment = detail().alignment!

  it('shows both sequences, the identity, and a way back to the raw text', () => {
    render(<AlignmentView alignment={alignment} />)
    expect(screen.getByRole('img', { name: /57% of columns identical/ })).toBeInTheDocument()
    // every column appears once in each row
    const rows = document.querySelectorAll('.align-row')
    expect(rows).toHaveLength(3) // query, connectors, target
    expect(rows[0]).toHaveTextContent('RRARVVW')
    expect(rows[2]).toHaveTextContent('RKARIAW')
    expect(screen.getAllByText('57%').length).toBeGreaterThan(0)
    expect(screen.getByText('86%')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('joins identical columns and marks conservative swaps differently', () => {
    const { container } = render(<AlignmentView alignment={alignment} />)
    // the midline is "|:||: |": four identical, two similar
    expect(container.querySelectorAll('.align-link.same')).toHaveLength(4)
    expect(container.querySelectorAll('.align-link.alike')).toHaveLength(2)
  })

  it('copies the raw text on request', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<AlignmentView alignment={alignment} />)
    await userEvent.click(screen.getByRole('button', { name: 'Copy raw' }))
    expect(writeText).toHaveBeenCalledWith(alignment.text)
    expect(await screen.findByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })
})

describe('property bars', () => {
  it('places a value inside the band of known AMPs', () => {
    const { container } = render(<PropertyBar name="net_charge" value={4} />)
    const dot = container.querySelector('.prop-dot') as HTMLElement
    expect(dot).not.toHaveClass('outside')
    expect(container.querySelector('.prop-bar')).toHaveAttribute(
      'title',
      'Within the range of most known AMPs',
    )
  })

  it('marks a value that sits outside it, on either side', () => {
    const low = render(<PropertyBar name="net_charge" value={-4} />)
    expect(low.container.querySelector('.prop-dot')).toHaveClass('outside')
    expect(low.container.querySelector('.prop-bar')).toHaveAttribute(
      'title',
      expect.stringContaining('lower'),
    )
    low.unmount()
    const high = render(<PropertyBar name="net_charge" value={20} />)
    expect(high.container.querySelector('.prop-bar')).toHaveAttribute(
      'title',
      expect.stringContaining('higher'),
    )
  })

  it('draws nothing for a property with no reference range', () => {
    const { container } = render(<PropertyBar name="not_a_property" value={1} />)
    expect(container).toBeEmptyDOMElement()
  })
})
