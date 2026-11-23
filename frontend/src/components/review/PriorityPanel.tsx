import {
  PRIORITY_LABELS,
  type FactorExplanations,
  type PriorityLevel,
  type PriorityRun,
  type PriorityState,
} from '../../services/raiseCapacityPriority'
import { priorityCheckActive } from '../../hooks/useRaiseCapacityPriority'
import { savedText, uncoveredEvidence } from '../../utils/raiseCapacityExplanations'
import { factorSignalDisplay } from '../../utils/priorityFactorSignals'
import { formatDateTime } from './format'

// The agent's seven factors, in the order of its saved result.
const FACTORS: [keyof FactorExplanations, string][] = [
  ['graduation', 'Graduation'],
  ['degree_progress', 'Degree progress'],
  ['course_requirement', 'Course requirement'],
  ['course_availability', 'Course availability'],
  ['previous_attempts', 'Previous attempts'],
  ['prerequisite', 'Prerequisite'],
  ['progression', 'Progression'],
]

interface PriorityPanelProps {
  status: 'loading' | 'ready' | 'error'
  data: PriorityState | null
  error: string | null
  /** This page's request to start a check is in flight. */
  running: boolean
  /** A problem with the latest action, shown beside the saved result. */
  notice: string | null
  /** Reloads the saved state after a read failure ("Try again"). */
  onRetry: () => void
  /** Re-evaluates a saved priority, or retries after a failed check. */
  onRerun: () => void
  /** The request already has a final status (it is not re-evaluated). */
  finalized: boolean
}

// The saved result as the Prioritization Agent stored it: level, reasoning, one
// card per factor and any key evidence the factor cards do not already state.
// Every explanation is shown in full, as saved (raw field flags in plain words).
// Each factor card is coloured by the agent's saved signal for that factor (its
// contribution to the priority, validated against the evidence when saved);
// without a valid saved signal the card is grey "Not classified". The colour is
// never derived from the explanation text or from the overall priority.
function PriorityCard({ level, data }: { level: PriorityLevel; data: PriorityState }) {
  const result = data.result
  const factors = result?.factor_explanations
  const evidence = (result?.key_evidence ?? []).filter((item) => item.trim() !== '')
  const shown = factors ? FACTORS.filter(([field]) => factors[field]) : []
  const reasoning = savedText(result?.reasoning)
  const factorTexts = shown.map(([field]) => savedText(factors![field]))
  const otherEvidence = uncoveredEvidence(evidence, factorTexts)

  // Two columns, as on the Course Equivalency review: the result on the left,
  // the factor cards stacked on the right.
  return (
    <div className="pcr-columns rca-columns">
      <div className="pcr-column">
        <span className="pcr-column__label">Priority result</span>
        <div className="rca-verdict">
          <span className="adm-prio-pill" data-level={level}>
            {PRIORITY_LABELS[level]}
          </span>
          {reasoning ? (
            <p className="pcr-summary rca-reasoning">{reasoning}</p>
          ) : (
            <p className="rv-muted">No reasoning was recorded.</p>
          )}
        </div>
        {otherEvidence.length > 0 && (
          <div className="rca-evidence">
            <p className="rca-evidence__title">Other key evidence</p>
            <ul className="rca-evidence__list">
              {otherEvidence.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="pcr-column pcr-column--last">
        <span className="pcr-column__label">Priority factors</span>
        {factors && shown.length > 0 ? (
          <div className="rca-factors">
            {shown.map(([field, label], index) => {
              const signal = factorSignalDisplay(result?.factor_signals, field)
              return (
                <section
                  key={field}
                  className="pcr-check rca-factor"
                  data-tone={signal.tone}
                  aria-labelledby={`rca-factor-${field}`}
                >
                  <div className="pcr-check__head">
                    <h4 id={`rca-factor-${field}`} className="pcr-check__name">
                      {label}
                    </h4>
                    <span className="pcr-check__status">
                      <span aria-hidden="true">{signal.glyph}</span>
                      {signal.label}
                    </span>
                  </div>
                  <p className="rca-factor__text">{factorTexts[index]}</p>
                </section>
              )
            })}
          </div>
        ) : (
          <p className="rv-muted">No factor explanations were recorded.</p>
        )}
      </div>
    </div>
  )
}

function NoAssessment() {
  return <p className="rv-muted">No priority assessment has been recorded for this request.</p>
}

// The outcome of the latest re-evaluation when it did not replace the saved result.
function LatestRerun({ run }: { run: PriorityRun }) {
  const when = formatDateTime(run.finished_at ?? run.started_at)
  if (run.status === 'discarded') {
    return (
      <div className="rv-alert" data-tone="technical" role="status">
        <p className="rv-alert__title">Latest re-evaluation was not saved{when ? ` (${when})` : ''}</p>
        <p className="rv-alert__body">
          {run.error_message ?? 'The new result was not saved.'} The result below has not been replaced.
        </p>
      </div>
    )
  }
  return (
    <div className="rv-alert" data-tone="failure" role="alert">
      <p className="rv-alert__title">
        {run.status === 'interrupted' ? 'Latest re-evaluation was interrupted' : 'Latest re-evaluation failed'}
        {when ? ` (${when})` : ''}
      </p>
      <p className="rv-alert__body">
        {run.error_message ?? 'The check did not finish.'} This is a technical failure, not a priority. The
        result below is the last successful assessment and has not been replaced.
      </p>
    </div>
  )
}

// One request's priority state, from the backend's state names.
function PriorityStateView({ data }: { data: PriorityState }) {
  switch (data.state) {
    case 'saved': {
      const run = data.last_run
      const unsuccessfulRerun =
        run?.trigger === 'rerun' && (run.status === 'failed' || run.status === 'interrupted' || run.status === 'discarded')
      return (
        <>
          {unsuccessfulRerun && <LatestRerun run={run} />}
          {data.priority ? <PriorityCard level={data.priority} data={data} /> : <NoAssessment />}
        </>
      )
    }
    case 'needs_attention':
      return (
        <div className="rv-alert" role="status">
          <p className="rv-alert__title">The saved priority needs attention</p>
          <p className="rv-alert__body">
            {data.attention_reason ?? 'The saved priority could not be shown.'} No priority is shown
            for this request.
          </p>
        </div>
      )
    case 'running':
      return null // the running message is shown by the panel
    case 'failed': {
      const interrupted = data.last_run?.status === 'interrupted'
      return (
        <div className="rv-alert" data-tone="failure" role="alert">
          <p className="rv-alert__title">
            {interrupted ? 'The latest priority check was interrupted' : 'The latest priority check failed'}
          </p>
          <p className="rv-alert__body">
            {data.last_run?.error_message ?? 'The check did not finish.'} This is a technical failure,
            not a priority.
          </p>
        </div>
      )
    }
    default:
      return <NoAssessment />
  }
}

// The Prioritization Agent's part of the AI Agent Evaluation: its saved
// assessment, read from the same endpoint as the requests table's Priority
// column. Re-evaluate runs the agent again for a saved priority (or retries a
// failed check); the saved result stays on screen until a new one replaces it,
// and a failed re-evaluation leaves it unchanged. A LOW priority is a ranking,
// not a failed eligibility check. Nothing here changes the request or its decision.
function PriorityPanel({ status, data, error, running, notice, onRetry, onRerun, finalized }: PriorityPanelProps) {
  const active = running || priorityCheckActive(data)
  const allowed = Boolean(data?.can_rerun || data?.can_retry) && !finalized
  const showButton = status === 'ready' && data !== null && ['saved', 'failed', 'running'].includes(data.state)
  const reason = finalized
    ? 'This request is no longer In Progress; its priority is not re-evaluated.'
    : active
      ? 'A priority check is running.'
      : !allowed
        ? 'The priority cannot be re-evaluated now.'
        : undefined

  return (
    <section className="rca-agent" aria-labelledby="rca-priority-title" aria-busy={active}>
      <div className="rca-agent__head">
        <h3 id="rca-priority-title" className="rca-agent__title">
          Prioritization Agent
        </h3>
        {showButton && (
          <button type="button" className="pcr-rerun" onClick={onRerun} disabled={active || !allowed} title={reason}>
            {active ? 'Evaluating…' : 'Re-evaluate'}
          </button>
        )}
      </div>

      {status === 'loading' && <p className="rv-muted" role="status">Loading the priority assessment…</p>}

      {status === 'error' && (
        <div className="rv-alert" data-tone="failure" role="alert">
          <p className="rv-alert__title">The priority assessment could not be loaded.</p>
          <p className="rv-alert__body">{error}</p>
          <button type="button" className="req-button" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && active && (
        <p className="rv-running" role="status">
          <span className="rv-running__dot" aria-hidden="true" />
          {data?.state === 'saved'
            ? 'Re-evaluating the priority. The result below is the previous assessment until the new one is saved.'
            : 'A priority check is running for this request. This section updates when it finishes.'}
        </p>
      )}

      {notice && (
        <p className="rv-notice" role="alert">
          {notice}
        </p>
      )}

      {status === 'ready' && (data ? <PriorityStateView data={data} /> : <NoAssessment />)}
    </section>
  )
}

export default PriorityPanel
