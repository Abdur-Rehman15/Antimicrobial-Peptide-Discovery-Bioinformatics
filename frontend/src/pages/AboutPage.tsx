import { api } from '../api/client'
import { ErrorNotice, Note, Spinner } from '../components/Bits'
import { PipelineStages } from '../components/PipelineStages'
import { NOVELTY_COLOR } from '../components/Chips'
import type { NoveltyClass } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { count } from '../lib/format'

function pct(x: number | undefined, digits = 0): string {
  return x === undefined ? '-' : `${(x * 100).toFixed(digits)}%`
}

/** A measure as a number with a bar, so a column can be read down at a glance. */
function Metric({ value, text }: { value: number | undefined; text: string }) {
  return (
    <span className="metric-cell">
      <span className="bar" aria-hidden style={{ '--w': `${(value ?? 0) * 100}%` } as React.CSSProperties} />
      {text}
    </span>
  )
}

export function AboutPage() {
  const info = useAsync((signal) => api.info(signal), [])
  const test = info.data?.activity_test
  const hemo = info.data?.hemolysis_test

  return (
    <div className="stack" style={{ maxWidth: 900 }}>
      <div>
        <h1>How this works</h1>
        <p className="lead" style={{ marginTop: 6 }}>
          Antimicrobial peptides (AMPs) kill bacteria and are a hope against drug-resistant
          infections. Some are hidden inside ordinary proteins and only become active when the
          protein is cut. This tool looks for them.
        </p>
      </div>

      <div className="card stack">
        <h2>The pipeline</h2>
        <PipelineStages horizontal idle />
        <p className="formula">
          activity<sup>a</sup>
          <span className="op">×</span>
          (1 − hemolysis risk)<sup>s</sup>
          <span className="op">×</span>
          novelty<sup>n</sup>
        </p>
      </div>

      {info.error && !info.data && <ErrorNotice error={info.error} title="Could not load the model details" />}
      {!info.data && !info.error && <Spinner label="Loading model details" />}

      {info.data && (
        <>
          <div className="card stack">
            <h2>How well does it work?</h2>
            <p className="muted">
              Measured on peptides the model never saw, scored once. “Recall at 1 in 1,000” is the
              share of real AMPs found when only 1 in 1,000 ordinary fragments is wrongly flagged.
            </p>
            {test && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Real AMPs</th>
                      <th className="num" scope="col">ROC AUC</th>
                      <th className="num" scope="col">PR AUC</th>
                      <th className="num" scope="col">Recall at 1 in 1,000</th>
                      <th className="num" scope="col">Recall at 1 in 10,000</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(['all', 'natural', 'synthetic'] as const).map((k) => (
                      <tr key={k}>
                        <td style={{ textTransform: 'capitalize' }}>{k}</td>
                        <td className="num">
                          <Metric value={test[k].roc_auc} text={test[k].roc_auc.toFixed(3)} />
                        </td>
                        <td className="num">
                          <Metric value={test[k].pr_auc} text={test[k].pr_auc.toFixed(3)} />
                        </td>
                        <td className="num">
                          <Metric
                            value={test[k]['recall@fpr=0.001']}
                            text={pct(test[k]['recall@fpr=0.001'])}
                          />
                        </td>
                        <td className="num">
                          <Metric
                            value={test[k]['recall@fpr=0.0001']}
                            text={pct(test[k]['recall@fpr=0.0001'])}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {hemo && (
              <p className="muted">
                Hemolysis model on {count(208)} test peptides: ROC AUC{' '}
                <strong>{hemo['ROC AUC']?.value.toFixed(2)}</strong> (95% interval{' '}
                {hemo['ROC AUC']?.ci95[0].toFixed(2)} to {hemo['ROC AUC']?.ci95[1].toFixed(2)}).
                That is better than guessing and far from certain: read it as a risk flag.
              </p>
            )}
          </div>

          <Note>{info.data.caveat}</Note>

          <div className="card stack">
            <h2>What the labels mean</h2>
            <div className="label-cards">
              {(Object.entries(info.data.novelty_labels) as [NoveltyClass, string][]).map(
                ([k, v]) => (
                  <div className="label-card" key={k}>
                    <span className="head">
                      <span className="dot" style={{ background: NOVELTY_COLOR[k] }} aria-hidden />
                      {k}
                    </span>
                    <span className="hint">{v}.</span>
                  </div>
                ),
              )}
            </div>
            <p className="muted">
              “Novel” does <em>not</em> mean “probably an AMP”. Half of all real AMPs are novel in
              this sense, because the known AMPs are a very incomplete list.
            </p>
          </div>

          <div className="card stack">
            <h2>Limits you should know about</h2>
            <ul className="plain">
              <li>
                A live run holds at most {count(info.data.limits.max_residues)} residues and{' '}
                {count(info.data.limits.max_proteins)} proteins (the scan covers about{' '}
                {count(info.data.limits.scan_speed_windows_per_second)} windows per second). Whole
                proteomes are scanned offline.
              </li>
              <li>
                The top of a scan holds many short (8 to 12 residue) candidates; isolated short
                hot spots each count as one candidate. Treat them with extra caution.
              </li>
              <li>
                The activity model finds fewer long (36 to 50) AMPs than short ones at a fixed
                false-alarm rate.
              </li>
              <li>
                The weights of the ranking are not fitted to data, because there is no ground truth
                for “the best candidate”. The top of the list is fairly stable when they change,
                but not completely.
              </li>
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
