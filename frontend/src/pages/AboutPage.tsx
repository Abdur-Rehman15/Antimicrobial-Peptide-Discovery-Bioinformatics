import { api } from '../api/client'
import { ErrorNotice, Note, Spinner } from '../components/Bits'
import { useAsync } from '../hooks/useAsync'
import { count } from '../lib/format'

function pct(x: number | undefined, digits = 0): string {
  return x === undefined ? '-' : `${(x * 100).toFixed(digits)}%`
}

export function AboutPage() {
  const info = useAsync((signal) => api.info(signal), [])
  const test = info.data?.activity_test
  const hemo = info.data?.hemolysis_test

  return (
    <div className="stack" style={{ maxWidth: 860 }}>
      <div>
        <h1>How this works</h1>
        <p className="muted" style={{ marginTop: 4 }}>
          Antimicrobial peptides (AMPs) kill bacteria and are a hope against drug-resistant
          infections. Some are hidden inside ordinary proteins and only become active when the
          protein is cut. This tool looks for them.
        </p>
      </div>

      <div className="card stack">
        <h2>The pipeline</h2>
        <ol className="plain" style={{ listStyle: 'decimal' }}>
          <li>
            <strong>Scan.</strong> Every fragment of 8 to 50 amino acids of every protein is
            described by 35 numbers (charge, oiliness, how amphipathic it is, composition) and
            scored by a gradient-boosting model trained on about 12,000 lab-tested AMPs.
          </li>
          <li>
            <strong>Merge.</strong> Overlapping fragments are one finding, so the best fragment of
            each region is kept.
          </li>
          <li>
            <strong>Check.</strong> A second model predicts hemolysis (damage to red blood cells).
            Our own Smith-Waterman alignment compares the fragment with 17,492 known AMPs to judge
            novelty.
          </li>
          <li>
            <strong>Rank.</strong> The three are combined; you control the weights.
          </li>
        </ol>
        {info.data && (
          <p className="mono" style={{ background: 'var(--wash)', padding: '8px 12px', borderRadius: 8 }}>
            {info.data.rank_formula}
          </p>
        )}
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
                        <td className="num">{test[k].roc_auc.toFixed(3)}</td>
                        <td className="num">{test[k].pr_auc.toFixed(3)}</td>
                        <td className="num">{pct(test[k]['recall@fpr=0.001'])}</td>
                        <td className="num">{pct(test[k]['recall@fpr=0.0001'])}</td>
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
            <ul className="plain">
              {Object.entries(info.data.novelty_labels).map(([k, v]) => (
                <li key={k}><strong style={{ textTransform: 'capitalize' }}>{k}:</strong> {v}.</li>
              ))}
              <li>
                “Novel” does <em>not</em> mean “probably an AMP”. Half of all real AMPs are novel
                in this sense, because the known AMPs are a very incomplete list.
              </li>
            </ul>
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
                The top of a scan holds many short (8 to 12 amino acid) candidates; isolated short
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
