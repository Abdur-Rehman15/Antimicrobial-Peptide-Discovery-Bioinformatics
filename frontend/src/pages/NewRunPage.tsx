import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Organism, RunSource } from '../api/types'
import { ErrorNotice, Note, Spinner } from '../components/Bits'
import { useAsync } from '../hooks/useAsync'
import { useDebounced } from '../hooks/useDebounced'
import { count, duration, estimatedSeconds, rarity } from '../lib/format'

type Mode = 'accessions' | 'fasta' | 'organism'

// UniProt's official accession format (https://www.uniprot.org/help/accession_numbers)
const ACCESSION = /^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})(-\d+)?$/i
const EXAMPLE = 'P69905, P02788, P59665, P06881'
const RARITIES = [1e-2, 1e-3, 1e-4]
const LIMIT_RESIDUES = 100_000

/** Split text into UniProt accessions and report the ones that do not look like accessions. */
export function parseAccessions(text: string): { valid: string[]; invalid: string[] } {
  const tokens = text.split(/[\s,;]+/).filter(Boolean)
  const valid: string[] = []
  const invalid: string[] = []
  for (const token of tokens) {
    if (ACCESSION.test(token)) {
      if (!valid.includes(token.toUpperCase())) valid.push(token.toUpperCase())
    } else {
      invalid.push(token)
    }
  }
  return { valid, invalid }
}

function OrganismPicker({
  chosen,
  onChoose,
}: {
  chosen: Organism | null
  onChoose: (organism: Organism) => void
}) {
  const [query, setQuery] = useState('')
  const debounced = useDebounced(query.trim(), 400)
  const search = useAsync((signal) => api.organisms(debounced, signal), [debounced], debounced.length >= 2)

  return (
    <div className="stack">
      <label className="field">
        Search an organism
        <input type="search" value={query} placeholder="e.g. escherichia coli, mouse, arabidopsis"
          onChange={(e) => setQuery(e.target.value)} />
        <span className="hint">
          Only reviewed (Swiss-Prot) proteins are used. A full proteome with unreviewed entries can
          hold hundreds of thousands of proteins.
        </span>
      </label>
      {search.loading && <Spinner label="Searching UniProt" />}
      {search.error && <ErrorNotice error={search.error} title="The search failed" />}
      {debounced.length >= 2 && search.data && !search.loading && search.data.length === 0 && (
        <p className="muted">No organism with reviewed proteins matches “{debounced}”.</p>
      )}
      {search.data && search.data.length > 0 && (
        <div className="card flush" role="radiogroup" aria-label="Organisms found">
          {search.data.map((o) => (
            <label key={o.taxon_id} className="check"
              style={{ padding: '10px 14px', borderBottom: '1px solid var(--grid)' }}>
              <input type="radio" name="organism" checked={chosen?.taxon_id === o.taxon_id}
                onChange={() => onChoose(o)} />
              <span style={{ flex: 1 }}>{o.name}</span>
              <span className="faint">
                {count(o.reviewed_proteins)} proteins · taxon {o.taxon_id}
              </span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

export function NewRunPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('accessions')
  const [accessionText, setAccessionText] = useState('')
  const [fasta, setFasta] = useState('')
  const [organism, setOrganism] = useState<Organism | null>(null)
  const [sample, setSample] = useState(100)
  const [topN, setTopN] = useState(200)
  const [prevalence, setPrevalence] = useState(1e-3)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const accessions = useMemo(() => parseAccessions(accessionText), [accessionText])
  const fastaProteins = (fasta.match(/^>/gm) ?? []).length

  let source: RunSource | null = null
  let problem: string | null = null
  if (mode === 'accessions') {
    if (accessions.invalid.length > 0) problem = `Not a UniProt accession: ${accessions.invalid.slice(0, 3).join(', ')}`
    else if (accessions.valid.length === 0) problem = 'Enter at least one accession.'
    else if (accessions.valid.length > 200) problem = 'At most 200 accessions per run.'
    else source = { type: 'accessions', accessions: accessions.valid }
  } else if (mode === 'fasta') {
    if (fasta.trim() === '') problem = 'Paste at least one protein in FASTA format.'
    else if (fastaProteins === 0) problem = 'FASTA starts each protein with a line beginning with “>”.'
    else source = { type: 'fasta', text: fasta }
  } else if (organism) {
    source = { type: 'organism', taxon_id: organism.taxon_id, max_proteins: sample }
  } else {
    problem = 'Search and pick an organism.'
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!source) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.createRun({
        source,
        options: { top_n: topN, prevalence },
        label: label.trim() || undefined,
      })
      navigate(`/runs/${created.id}`)
    } catch (err) {
      setError(err as Error)
      setBusy(false)
    }
  }

  const sampleSeconds = estimatedSeconds(Math.min(sample, organism?.reviewed_proteins ?? sample))

  return (
    <form onSubmit={submit} className="stack" style={{ maxWidth: 820 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1>New run</h1>
          <p className="lead">
            Every possible fragment of 8 to 50 residues is scored, then the best regions are checked
            for toxicity and novelty.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="tabs" role="tablist" aria-label="Where the proteins come from">
          {(
            [
              ['accessions', 'UniProt accessions'],
              ['fasta', 'Paste FASTA'],
              ['organism', 'Organism'],
            ] as const
          ).map(([value, text]) => (
            <button key={value} type="button" role="tab" aria-selected={mode === value}
              onClick={() => setMode(value)}>
              {text}
            </button>
          ))}
        </div>
        <div style={{ paddingTop: 16 }} className="stack">
          {mode === 'accessions' && (
            <label className="field">
              Accessions
              <textarea value={accessionText} style={{ minHeight: 96 }}
                placeholder={EXAMPLE} onChange={(e) => setAccessionText(e.target.value)} />
              <span className="hint">
                Separate with commas, spaces or new lines.{' '}
                <button type="button" className="quiet" style={{ padding: 0 }}
                  onClick={() => setAccessionText(EXAMPLE)}>
                  Use an example
                </button>
              </span>
            </label>
          )}
          {mode === 'fasta' && (
            <label className="field">
              Proteins in FASTA format
              <textarea value={fasta} placeholder={'>sp|P12345|MY_PROTEIN My protein\nMKT...'}
                onChange={(e) => setFasta(e.target.value)} />
              <span className="hint">
                {fastaProteins > 0 ? `${fastaProteins} protein(s) found. ` : ''}
                One live run takes up to {count(LIMIT_RESIDUES)} residues (about 4 minutes).
              </span>
            </label>
          )}
          {mode === 'organism' && (
            <>
              <OrganismPicker chosen={organism} onChoose={setOrganism} />
              {organism && (
                <label className="field">
                  How many proteins to scan (random sample of {count(organism.reviewed_proteins)})
                  <input type="number" min={1} max={500} value={sample}
                    onChange={(e) => setSample(Math.min(500, Math.max(1, Number(e.target.value) || 1)))} />
                  <span className="hint">
                    About {duration(sampleSeconds)}. A whole proteome is an offline job
                    (scripts/precompute_run.py).
                  </span>
                </label>
              )}
            </>
          )}
          {problem && <p className="hint" role="status">{problem}</p>}
        </div>
      </div>

      <div className="card stack">
        <h2>Options</h2>
        <div className="two-col">
          <label className="field">
            Name (optional)
            <input type="text" value={label} maxLength={120} placeholder="e.g. Human blood proteins"
              onChange={(e) => setLabel(e.target.value)} />
          </label>
          <label className="field">
            Candidates to keep
            <input type="number" min={1} max={1000} value={topN}
              onChange={(e) => setTopN(Math.min(1000, Math.max(1, Number(e.target.value) || 1)))} />
            <span className="hint">The best regions after overlapping windows are merged.</span>
          </label>
          <label className="field">
            Assumed rarity of AMPs
            <select value={prevalence} onChange={(e) => setPrevalence(Number(e.target.value))}>
              {RARITIES.map((r) => (
                <option key={r} value={r}>{rarity(r)} windows</option>
              ))}
            </select>
            <span className="hint">Sets the calibrated activity number. It can be changed later.</span>
          </label>
        </div>
      </div>

      <Note>
        Scores are model estimates. “Novel” means unlike every known AMP, not “probably an AMP”.
        Hemolysis is only roughly predicted. Treat the list as a place to look, not a verdict.
      </Note>
      {error && <ErrorNotice error={error} title="The run could not be started" />}
      <div className="row">
        <button type="submit" className="primary" disabled={!source || busy}>
          {busy ? 'Starting…' : 'Start run'}
        </button>
      </div>
    </form>
  )
}
