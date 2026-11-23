import { formatDateTime } from '../review/format'
import {
  CHECK_STATUS_TONE,
  LEGACY_MANUAL_START_NOTICE,
  FAILURE_NOTES,
  RECOMMENDATION_DISPLAY,
  SAFEGUARD_EXPLANATION_KEYS,
  SIMILARITY_CHECKS,
  SIMILARITY_COMPONENTS,
  evaluationPanelView,
  explanationsByCheck,
  matchSummary,
  outdatedMessage,
  rejectionSuggestions,
  safeguardChecks,
  scoreBandLabel,
  type CheckTone,
  type CourseEquivalencyCheckExplanation,
  type CourseEquivalencyEvaluationState,
  type CourseEquivalencyRun,
} from '../../utils/courseEquivalencyEvaluation'
import type { SyllabusSide } from '../../utils/courseEquivalencyEvaluation'

const CHECK_STATUS: Record<CheckTone, { glyph: string; label: string }> = {
  pass: { glyph: '✓', label: 'PASSED' },
  fail: { glyph: '✕', label: 'FAILED' },
  unknown: { glyph: '–', label: 'NOT CONFIRMED' },
}

interface EvaluationPanelProps {
  status: 'loading' | 'ready' | 'error'
  data: CourseEquivalencyEvaluationState | null
  error: string | null
  running: boolean
  notice: string | null
  canStartFirst: boolean
  canRerun: boolean
  onRun: (rerun: boolean) => void
  onRetry: () => void
  /** Fills the decision with a suggested reason (selects Reject; staff can still edit it), or
   *  null when the request cannot be decided now or the decision is being confirmed. */
  onUseReason?: ((text: string) => void) | null
  /** The syllabus sides with no current file (from the syllabi state), or null while unknown. */
  missingSyllabi?: readonly SyllabusSide[] | null
}

function DocumentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  )
}

const SIDE_NAMES: Record<SyllabusSide, string> = { old: 'Old syllabus', new: 'New syllabus' }

// Both syllabi are needed before the evaluation can run: a calm, centered empty state that
// names which syllabus is missing.
function WaitingForSyllabi({ missing }: { missing: readonly SyllabusSide[] | null }) {
  return (
    <div className="cer-waiting" role="status">
      <span className="cer-waiting__icon">
        <DocumentIcon />
      </span>
      <span className="cer-waiting__title">Waiting for course syllabi</span>
      <span className="cer-waiting__text">Upload both the old and new course syllabi to run the AI evaluation.</span>
      {missing && (
        <ul className="cer-waiting__status" aria-label="Syllabus status">
          {(['old', 'new'] as const).map((side) => {
            const isMissing = missing.includes(side)
            return (
              <li key={side} className="cer-waiting__pill" data-state={isMissing ? 'missing' : 'ready'}>
                <span aria-hidden="true">{isMissing ? '○' : '✓'}</span>
                {SIDE_NAMES[side]}: {isMissing ? 'missing' : 'uploaded'}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// The agent's two syllabus checks (by identifier), under the similarity bars: status and
// explanation, green for PASS and red for FAIL.
function SyllabusChecks({ explanations }: { explanations: Map<string, CourseEquivalencyCheckExplanation> }) {
  return (
    <ul className="cer-sim-checks">
      {SIMILARITY_CHECKS.map(({ key, name }) => {
        const e = explanations.get(key)
        const tone = e ? (CHECK_STATUS_TONE[e.status] ?? 'unknown') : 'unknown'
        return (
          <li key={key} className="pcr-check cer-sim-check" data-tone={tone}>
            <div className="pcr-check__head">
              <span className="pcr-check__name">{name}</span>
              <span className="pcr-check__status">
                <span aria-hidden="true">{CHECK_STATUS[tone].glyph}</span>
                {e ? e.status : 'NOT RECORDED'}
              </span>
            </div>
            <span className="pcr-check__detail">{e?.explanation?.trim() || 'No explanation was recorded.'}</span>
          </li>
        )
      })}
    </ul>
  )
}

function Similarity({ run, explanations }: { run: CourseEquivalencyRun; explanations: Map<string, CourseEquivalencyCheckExplanation> }) {
  const sim = run.deterministic_results?.similarity ?? null
  const request = run.deterministic_results?.syllabus_request
  if (!sim) {
    return (
      <div className="cer-similarity">
        <span className="pcr-column__label">Syllabus similarity</span>
        <p className="rv-muted">{request ?? 'No similarity score was calculated for this evaluation.'}</p>
        <SyllabusChecks explanations={explanations} />
      </div>
    )
  }
  const summary = matchSummary(sim)
  return (
    <div className="cer-similarity">
      <span className="pcr-column__label">Syllabus similarity (calculated by code from the AI’s verified matches)</span>
      <div className="cer-similarity__overall">
        <span className="cer-similarity__value">
          {sim.overall_similarity_percent === null ? '—' : `${sim.overall_similarity_percent}%`}
        </span>
        <span className="cer-similarity__band">{scoreBandLabel(sim)}</span>
      </div>
      <dl className="cer-components">
        {SIMILARITY_COMPONENTS.map((c) => {
          const value = sim.components_percent[c.key]
          return (
            <div key={c.key} className="cer-components__item">
              <dt>
                {c.label} <span className="rv-muted">(weight {c.weight}%)</span>
              </dt>
              <dd>
                <span className="cer-meter" aria-hidden="true">
                  <span className="cer-meter__bar" style={{ width: `${value ?? 0}%` }} />
                </span>
                {value === null ? 'Not stated' : `${value}%`}
              </dd>
            </div>
          )
        })}
      </dl>
      {summary && <p className="rv-muted">{summary}</p>}
      {sim.verification_ok === false && (
        <p className="pcr-warning" role="note">
          <span aria-hidden="true">! </span>Many of the AI’s matches could not be confirmed in the syllabus text, so approval was withheld.
        </p>
      )}
      {sim.credit_hours.note && <p className="rv-muted">{sim.credit_hours.note}</p>}
      <SyllabusChecks explanations={explanations} />
      {(sim.new_topics_not_covered.length > 0 || sim.new_outcomes_not_covered.length > 0) && (
        <div className="cer-uncovered">
          {sim.new_topics_not_covered.length > 0 && (
            <>
              <span className="pcr-column__label">Requested-course topics not covered</span>
              <ul>{sim.new_topics_not_covered.map((t, i) => <li key={`t${i}`}>{t}</li>)}</ul>
            </>
          )}
          {sim.new_outcomes_not_covered.length > 0 && (
            <>
              <span className="pcr-column__label">Learning outcomes not covered</span>
              <ul>{sim.new_outcomes_not_covered.map((t, i) => <li key={`o${i}`}>{t}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function Suggestions({ run, onUseReason }: { run: CourseEquivalencyRun; onUseReason: ((text: string) => void) | null }) {
  const s = rejectionSuggestions(run)
  if (!s) return null
  return (
    <div className="ier-suggest" aria-labelledby="cer-suggest-title">
      <div className="ier-suggest__head">
        <span id="cer-suggest-title" className="pcr-column__label">
          Suggested explanations to the student
        </span>
      </div>
      {s.judged.length > 0 && (
        <p className="ier-suggest__basis">
          <strong>Assessed reasons:</strong> {s.judged.join('; ')} <span className="rv-muted">(the AI’s assessment, not a verified record)</span>
        </p>
      )}
      {s.statusNote && <p className="rv-muted">{s.statusNote}</p>}
      {s.reasons.length > 0 && (
        <ul className="ier-suggest__list">
          {s.reasons.map((reason, index) => (
            <li key={`${reason.tone}-${index}`} className="ier-suggest__item">
              <span className="ier-suggest__tone">{reason.label}</span>
              <p className="ier-suggest__text">{reason.text}</p>
              {onUseReason && (
                <button type="button" className="pcr-rerun" onClick={() => onUseReason(reason.text)}>
                  Use this reason
                  <span className="student-visually-hidden"> ({reason.label})</span>
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!onUseReason && s.reasons.length > 0 && (
        <span className="rv-muted">Suggestions can be used only while the request is awaiting a decision.</span>
      )}
      {s.notes.length > 0 && <p className="rv-muted">{s.notes.join(' ')}</p>}
    </div>
  )
}

// A completed evaluation. Top: the recommendation (left) and the academic safeguards, each
// with the agent's explanation for that check (right). Below: the similarity (with the
// agent's two syllabus checks) and the suggested explanations. The stored evidence is not
// shown here (it stays in the evaluation record).
function Results({ run, onUseReason }: { run: CourseEquivalencyRun; onUseReason: ((text: string) => void) | null }) {
  const rec = run.recommendation ? RECOMMENDATION_DISPLAY[run.recommendation] : null
  const checks = safeguardChecks(run.deterministic_results)
  const { byKey, other } = explanationsByCheck(run.check_explanations)
  return (
    <>
      <div className="pcr-columns cer-top">
        <div className="pcr-column">
          <span className="pcr-column__label">Agent recommendation</span>
          {rec ? (
            <span className="pcr-verdict" data-tone={rec.tone}>
              <span aria-hidden="true">{rec.glyph}</span>
              {rec.label}
            </span>
          ) : (
            <span className="pcr-verdict" data-tone="none">Not recorded</span>
          )}
          {rec && <span className="rv-muted">{rec.meaning}</span>}
          {run.reasoning ? <p className="pcr-summary">{run.reasoning}</p> : <p className="rv-muted">No reasoning was recorded.</p>}
        </div>
        <div className="pcr-column pcr-column--last">
          <span className="pcr-column__label">Academic safeguards (verified by code)</span>
          {checks ? (
            checks.map((check) => {
              const status = CHECK_STATUS[check.tone]
              const explanation = byKey.get(SAFEGUARD_EXPLANATION_KEYS[check.key] ?? check.key)
              const text = explanation?.explanation?.trim()
              const agentTone = explanation ? CHECK_STATUS_TONE[explanation.status] : undefined
              return (
                <div key={check.key} className="pcr-check" data-tone={check.tone}>
                  <div className="pcr-check__head">
                    <span className="pcr-check__name">{check.name}</span>
                    <span className="pcr-check__status">
                      <span aria-hidden="true">{status.glyph}</span>
                      {status.label}
                    </span>
                  </div>
                  <span className="ier-check__value">{check.value}</span>
                  {/* The agent's explanation of this check; the code's description when there is none. */}
                  <span className="pcr-check__detail">{text || check.detail}</span>
                  {explanation && agentTone && agentTone !== check.tone && (
                    <span className="cer-check__agent">Agent’s assessment: {explanation.status}</span>
                  )}
                </div>
              )
            })
          ) : (
            <p className="rv-muted">No verified checks were recorded.</p>
          )}
          {other.length > 0 && (
            <dl className="ier-explanations cer-other-checks" aria-label="Other agent checks">
              {other.map((e, i) => (
                <div key={`${e.name}-${i}`} className="ier-explanations__item" data-tone={CHECK_STATUS_TONE[e.status] ?? 'unknown'}>
                  <dt>
                    {e.name.replace(/_/g, ' ')} · {e.status}
                  </dt>
                  <dd>{e.explanation?.trim() || 'Not recorded'}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
      <Similarity run={run} explanations={byKey} />
      <Suggestions run={run} onUseReason={onUseReason} />
    </>
  )
}

// The Course Equivalency agents' evaluation (eligibility + rejection explanations), from the
// backend. The first evaluation starts automatically only when the backend reports it
// eligible (once); staff can re-evaluate when it is allowed. Everything is advisory.
function EvaluationPanel({
  status, data, error, running, notice, canStartFirst, canRerun, onRun, onRetry, onUseReason = null, missingSyllabi = null,
}: EvaluationPanelProps) {
  const view = evaluationPanelView(status, data, running)
  const { current, failedAttempt } = view
  // No evaluation yet and a syllabus missing: the centered empty state replaces the warnings.
  const waiting = view.stage === 'syllabi_missing' && !view.finalized
  const lastEvaluated = formatDateTime(current?.finished_at)
  const rerunAllowed = canRerun && !view.finalized
  return (
    <section className="pcr-ai" aria-labelledby="cer-ai-title" aria-busy={view.stage === 'running'}>
      <div className="pcr-ai__head">
        <div className="pcr-ai__heading">
          <h2 id="cer-ai-title" className="pcr-ai__title">
            AI Agent Evaluation
          </h2>
          <span className="pcr-ai__agent">Course Equivalency Eligibility Agent · advisory</span>
        </div>
        {(current || failedAttempt) && (
          <div className="pcr-ai__tools">
            {lastEvaluated && <span className="pcr-ai__generated">Last evaluated {lastEvaluated}</span>}
            <button
              type="button"
              className="pcr-rerun"
              onClick={() => onRun(true)}
              disabled={!rerunAllowed}
              title={
                view.finalized
                  ? 'This request is no longer In Progress; it is not evaluated again.'
                  : view.stage === 'running'
                    ? 'An evaluation is running.'
                    : !rerunAllowed
                      ? 'Re-evaluation needs both syllabi and the request details.'
                      : undefined
              }
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />
              </svg>
              {view.stage === 'running' ? 'Evaluating…' : 'Re-evaluate'}
            </button>
          </div>
        )}
      </div>

      {view.stage === 'loading' && (
        <p className="pcr-state" role="status">
          Loading the saved evaluation…
        </p>
      )}
      {view.stage === 'error' && (
        <div className="pcr-state pcr-state--error" role="alert">
          <div className="pcr-state__text">
            <span className="pcr-state__title">! The evaluation could not be loaded</span>
            <span className="pcr-state__body">{error}</span>
          </div>
          <button type="button" className="pcr-primary" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
      {view.detailsMissing && (
        <p className="rv-notice pcr-notice" role="alert">
          {data?.details_missing_message ?? 'This request has no Course Equivalency details, so it cannot be evaluated.'}
        </p>
      )}
      {waiting && (
        <WaitingForSyllabi missing={missingSyllabi} />
      )}
      {view.syllabiMissing && !view.detailsMissing && !waiting && (
        <p className="rv-notice pcr-notice" role="status">
          {data?.syllabi_missing_message ?? 'Both syllabi are required before the eligibility check can run.'}
        </p>
      )}
      {view.stage === 'running' && (
        <div className="pcr-state" role="status" aria-live="polite">
          <span className="pcr-state__running">
            <span className="pcr-spinner" aria-hidden="true" />
            Evaluating eligibility…
          </span>
          <span className="pcr-state__body">
            {running
              ? 'The agent is reading both syllabi, comparing them and checking the academic rules. This can take a minute or two; keep this page open.'
              : 'An evaluation is already running for this request. This page updates when it finishes.'}
          </span>
        </div>
      )}
      {notice && (
        <p className="rv-notice pcr-notice" role="alert">
          {notice}
        </p>
      )}
      {current && view.outdated && view.stage !== 'running' && (
        <p className="pcr-warning cer-outdated" role="alert">
          <span aria-hidden="true">! </span>
          {outdatedMessage(view.outdatedSides)}
        </p>
      )}
      {view.preservedAfterFailure && failedAttempt && view.stage !== 'running' && (
        <p className="rv-notice pcr-notice" role="alert">
          The latest re-evaluation{formatDateTime(failedAttempt.finished_at) ? ` (${formatDateTime(failedAttempt.finished_at)})` : ''} did
          not complete: {failedAttempt.error_message ?? 'the evaluation did not finish.'}{' '}
          {FAILURE_NOTES[failedAttempt.failure_kind ?? 'technical'] ?? FAILURE_NOTES.technical} The result below is the last successful
          evaluation and has not been replaced.
        </p>
      )}
      {view.stage === 'failed' && failedAttempt && (
        <div className="pcr-state pcr-state--error" role="alert">
          <div className="pcr-state__text">
            <span className="pcr-state__title">! The evaluation couldn’t be completed</span>
            <span className="pcr-state__body">
              {failedAttempt.error_message ?? 'The evaluation did not finish.'}{' '}
              {FAILURE_NOTES[failedAttempt.failure_kind ?? 'technical'] ?? FAILURE_NOTES.technical} No recommendation was recorded.
            </span>
          </div>
          {rerunAllowed && (
            <button type="button" className="pcr-primary" onClick={() => onRun(true)}>
              Re-evaluate
            </button>
          )}
        </div>
      )}
      {view.stage === 'not_evaluated' && (
        <div className="pcr-state pcr-state--empty">
          <p className="pcr-state__body">
            {view.finalized
              ? 'No evaluation was recorded for this request. Evaluations run only while a request is In Progress.'
              : view.manualStartRequired
                ? LEGACY_MANUAL_START_NOTICE
                : 'This request has not been evaluated yet. The evaluation starts automatically once both syllabi are uploaded.'}
          </p>
          {canStartFirst && !view.finalized && (
            <button type="button" className="pcr-primary" onClick={() => onRun(false)}>
              Run Evaluation
            </button>
          )}
        </div>
      )}
      {current && <Results run={current} onUseReason={onUseReason} />}
    </section>
  )
}

export default EvaluationPanel
