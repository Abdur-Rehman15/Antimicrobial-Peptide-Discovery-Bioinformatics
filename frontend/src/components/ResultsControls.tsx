import type { NoveltyClass, ProteinSummary, View } from '../api/types'
import { rarity } from '../lib/format'
import {
  DEFAULT_VIEW,
  MAX_WEIGHT,
  changedCount,
  prevalenceToSlider,
  sliderToPrevalence,
} from '../lib/view'
import { NOVELTY_COLOR, NOVELTY_HELP, NOVELTY_LABEL } from './Chips'

interface Props {
  view: View
  onChange: (view: View) => void
  proteins: ProteinSummary[] | null
}

const CLASSES: NoveltyClass[] = ['novel', 'related', 'known']

function Slider({
  id,
  label,
  help,
  value,
  min,
  max,
  step,
  display,
  onChange,
}: {
  id: string
  label: string
  help: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (value: number) => void
}) {
  return (
    <div>
      <div className="slider-head">
        <label htmlFor={id}>{label}</label>
        <output htmlFor={id}>{display}</output>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} />
      <p className="hint">{help}</p>
    </div>
  )
}

function numberOrNull(text: string): number | null {
  if (text.trim() === '') return null
  const value = Number(text)
  return Number.isFinite(value) ? value : null
}

/** Everything here only re-ranks or filters the saved shortlist; nothing is rescanned. */
export function ResultsControls({ view, onChange, proteins }: Props) {
  const set = (patch: Partial<View>) => onChange({ ...view, ...patch })
  const changed = changedCount(view)
  // `novelty: []` means "all classes". The last remaining class cannot be switched off, and
  // switching the third one back on returns to "all".
  const toggleClass = (cls: NoveltyClass) => {
    const next = view.novelty.includes(cls)
      ? view.novelty.filter((c) => c !== cls)
      : [...view.novelty, cls]
    if (next.length === 0) return
    set({ novelty: next.length === CLASSES.length ? [] : next })
  }
  const hemolysisChoice =
    view.maxHemolysis === null ? 'any' : view.maxHemolysis <= 0.33 ? 'low' : 'medium'

  return (
    <aside className="card" aria-label="Ranking and filters">
      <div className="row spread" style={{ marginBottom: 12 }}>
        <h2>Ranking</h2>
        <button className="quiet" onClick={() => onChange(DEFAULT_VIEW)} disabled={changed === 0}>
          Reset{changed > 0 ? ` (${changed})` : ''}
        </button>
      </div>
      <p className="hint" style={{ marginBottom: 12 }}>
        score = activity<sup>a</sup> × (1 − hemolysis risk)<sup>s</sup> × novelty<sup>n</sup>.
        The weights are not fitted to data: move them and watch the order change.
      </p>

      <div className="control-group">
        <Slider id="w-activity" label="Activity weight (a)" value={view.activityWeight}
          min={0} max={MAX_WEIGHT} step={0.1} display={view.activityWeight.toFixed(1)}
          help="How much the antimicrobial score counts."
          onChange={(v) => set({ activityWeight: v })} />
        <Slider id="w-safety" label="Safety weight (s)" value={view.safetyWeight}
          min={0} max={MAX_WEIGHT} step={0.1} display={view.safetyWeight.toFixed(1)}
          help="How much a low hemolysis risk counts. 0 ignores toxicity."
          onChange={(v) => set({ safetyWeight: v })} />
        <Slider id="w-novelty" label="Novelty weight (n)" value={view.noveltyWeight}
          min={0} max={MAX_WEIGHT} step={0.1} display={view.noveltyWeight.toFixed(1)}
          help="How much being unlike known AMPs counts. 0 ignores novelty."
          onChange={(v) => set({ noveltyWeight: v })} />
      </div>

      <div className="control-group">
        <Slider id="w-prevalence" label="Assumed rarity of AMPs"
          value={prevalenceToSlider(view.prevalence)} min={-5} max={-1} step={0.25}
          display={rarity(view.prevalence)}
          help="Sets the calibrated activity number. The real rarity is unknown, and it changes the order because it changes how strongly activity counts against safety."
          onChange={(v) => set({ prevalence: sliderToPrevalence(v) })} />
      </div>

      <div className="control-group">
        <h3>Filters</h3>
        <div className="checks" role="group" aria-label="Novelty classes">
          {CLASSES.map((cls) => {
            const on = view.novelty.length === 0 || view.novelty.includes(cls)
            return (
              <label key={cls} className="check" title={NOVELTY_HELP[cls]}>
                <input type="checkbox" checked={on && !(cls === 'known' && view.hideKnown)}
                  disabled={cls === 'known' && view.hideKnown}
                  onChange={() => {
                    // from "all" to "all but this one": list the other classes explicitly
                    if (view.novelty.length === 0) {
                      set({ novelty: CLASSES.filter((c) => c !== cls) })
                    } else {
                      toggleClass(cls)
                    }
                  }} />
                <span className="dot" style={{ background: NOVELTY_COLOR[cls] }} aria-hidden />
                {NOVELTY_LABEL[cls]}
              </label>
            )
          })}
          <label className="check">
            <input type="checkbox" checked={view.hideKnown}
              onChange={(e) => set({ hideKnown: e.target.checked })} />
            Hide known AMPs
          </label>
        </div>

        <label className="field">
          Hemolysis risk
          <select value={hemolysisChoice}
            onChange={(e) =>
              set({ maxHemolysis: { any: null, low: 0.33, medium: 0.66 }[e.target.value] ?? null })}>
            <option value="any">Any</option>
            <option value="low">Low only</option>
            <option value="medium">Low or medium</option>
          </select>
        </label>

        <div className="row" style={{ alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: 1 }}>
            Min length
            <input type="number" min={8} max={50} placeholder="8" value={view.minLength ?? ''}
              onChange={(e) => set({ minLength: numberOrNull(e.target.value) })} />
          </label>
          <label className="field" style={{ flex: 1 }}>
            Max length
            <input type="number" min={8} max={50} placeholder="50" value={view.maxLength ?? ''}
              onChange={(e) => set({ maxLength: numberOrNull(e.target.value) })} />
          </label>
        </div>

        {proteins && proteins.length > 1 && (
          <label className="field">
            Protein
            <select value={view.accession ?? ''}
              onChange={(e) => set({ accession: e.target.value || null })}>
              <option value="">All {proteins.length} proteins</option>
              {proteins.map((p) => (
                <option key={p.accession} value={p.accession}>
                  {p.accession} · {p.name.slice(0, 32)} ({p.n_candidates})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
    </aside>
  )
}
