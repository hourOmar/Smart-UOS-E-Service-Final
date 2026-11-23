import type { EvaluationRun, EvaluationState, Recommendation } from '../../services/raiseCapacityReview'
import { formatDateTime } from './format'
import EligibilityChecks from './EligibilityChecks'
import { savedText } from '../../utils/raiseCapacityExplanations'

const RECOMMENDATIONS: Record<Recommendation, { tone: string; glyph: string; label: string }> = {
  APPROVE: { tone: 'approve', glyph: '✓', label: 'APPROVE' },
  REJECT: { tone: 'reject', glyph: '✕', label: 'REJECT' },
  MANUAL_REVIEW: { tone: 'review', glyph: '!', label: 'MANUAL REVIEW' },
}

interface EligibilityPanelProps {
  status: 'loading' | 'ready' | 'error'
  data: EvaluationState | null
  error: string | null
  running: boolean
  notice: string | null
  onRerun: () => void
  onRetry: () => void
  /** The request already has a final status (no automatic check). */
  finalized: boolean
  /** Names of the prerequisite courses, for the check cards. */
  courseNames: Map<string, string>
}

// When the evaluation ran: its evidence is a snapshot from that time, not current records.
function Snapshot({ run }: { run: EvaluationRun }) {
  const when = formatDateTime(run.evidence?.collected_at ?? run.evaluated_at)
  return (
    <p className="rca-snapshot">
      <span className="rv-snapshot__tag">Snapshot</span>
      Evidence recorded by the eligibility check{when ? ` on ${when}` : ''}; it does not change when records change.
    </p>
  )
}

// A completed run whose decision Gemini could not make: evidence only.
function NoAutomatedDecision() {
  return (
    <div className="rv-alert" data-tone="technical" role="status">
      <p className="rv-alert__title">No automated recommendation</p>
      <p className="rv-alert__body">
        The decision service (Gemini) was unavailable when this check ran, so only the evidence
        was collected. This is a technical gap, not a Manual Review recommendation. Review the
        evidence yourself or re-run the check.
      </p>
    </div>
  )
}

function Result({ run, courseNames }: { run: EvaluationRun; courseNames: Map<string, string> }) {
  const decided = run.gemini_status === 'ok' && run.recommendation
  const rec = decided ? RECOMMENDATIONS[run.recommendation!] : null
  // Two columns, as on the Course Equivalency review: the recommendation on the
  // left, the three check cards stacked on the right (with their snapshot note).
  return (
    <div className="pcr-columns rca-columns">
      <div className="pcr-column">
        <span className="pcr-column__label">Agent recommendation</span>
        {rec ? (
          <div className="rca-verdict">
            <span className="pcr-verdict" data-tone={rec.tone}>
              <span aria-hidden="true">{rec.glyph}</span>
              {rec.label}
            </span>
            {savedText(run.reasoning) ? (
              <p className="pcr-summary rca-reasoning">{savedText(run.reasoning)}</p>
            ) : (
              <p className="rv-muted">No reasoning was recorded.</p>
            )}
          </div>
        ) : (
          <NoAutomatedDecision />
        )}
      </div>
      <div className="pcr-column pcr-column--last">
        <span className="pcr-column__label">Eligibility checks</span>
        {run.evidence?.checks && <Snapshot run={run} />}
        <EligibilityChecks run={run} names={courseNames} />
      </div>
    </div>
  )
}

// A newer attempt that did not replace the result above.
function LatestAttempt({ run, hasCurrent }: { run: EvaluationRun; hasCurrent: boolean }) {
  if (run.run_status === 'running') return null
  const kept = hasCurrent ? ' The result above is the last successful check and has not been replaced.' : ''
  if (run.run_status === 'completed') {
    return (
      <div className="rv-alert" data-tone="technical" role="status">
        <p className="rv-alert__title">Latest re-run produced no automated recommendation</p>
        <p className="rv-alert__body">
          Gemini was unavailable{run.evaluated_at ? ` at ${formatDateTime(run.evaluated_at)}` : ''}.{kept}
        </p>
      </div>
    )
  }
  const when = formatDateTime(run.evaluated_at ?? run.started_at)
  return (
    <div className="rv-alert" data-tone="failure" role="alert">
      <p className="rv-alert__title">
        {run.run_status === 'interrupted' ? 'Latest check was interrupted' : 'Latest check failed'}
        {when ? ` (${when})` : ''}
      </p>
      <p className="rv-alert__body">
        {run.error_message ?? 'The check did not finish.'} This is a technical failure, not a
        recommendation.{kept}
      </p>
    </div>
  )
}

// The Eligibility Agent's part of the AI Agent Evaluation: recommendation, reasoning and the
// three academic checks (each with its evidence and the agent's explanation). The check can be
// re-run here, as before.
function EligibilityPanel({ status, data, error, running, notice, onRerun, onRetry, finalized, courseNames }: EligibilityPanelProps) {
  const active = running || Boolean(data?.in_progress)
  const current = data?.current ?? null
  const attempt = data?.latest_attempt ?? null

  return (
    <section className="rca-agent" aria-labelledby="rca-eligibility-title" aria-busy={active}>
      <div className="rca-agent__head">
        <h3 id="rca-eligibility-title" className="rca-agent__title">
          Eligibility Agent
        </h3>
        {status !== 'loading' && !(status === 'error' && !data) && (
          <button type="button" className="pcr-rerun" onClick={onRerun} disabled={active}>
            {active ? 'Evaluating…' : 'Re-evaluate'}
          </button>
        )}
      </div>

      {status === 'loading' && <p className="rv-muted" role="status">Loading the eligibility check…</p>}

      {status === 'error' && !data && (
        <div className="rv-alert" data-tone="failure" role="alert">
          <p className="rv-alert__title">The eligibility check could not be loaded.</p>
          <p className="rv-alert__body">{error}</p>
          <button type="button" className="req-button" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}

      {active && (
        <p className="rv-running" role="status">
          <span className="rv-running__dot" aria-hidden="true" />
          {running
            ? 'Running the eligibility check. This can take up to a minute.'
            : 'An eligibility check is already running for this request. This page updates when it finishes.'}
        </p>
      )}

      {notice && (
        <p className="rv-notice" role="alert">
          {notice}
        </p>
      )}

      {current && <Result run={current} courseNames={courseNames} />}
      {attempt && <LatestAttempt run={attempt} hasCurrent={Boolean(current)} />}

      {status === 'ready' && data && !current && !attempt && !active && (
        <p className="rv-muted">
          {finalized ? 'No eligibility evaluation recorded.' : 'No eligibility check has been run for this request yet.'}
        </p>
      )}
    </section>
  )
}

export default EligibilityPanel
