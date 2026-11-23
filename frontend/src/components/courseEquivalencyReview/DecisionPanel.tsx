import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { CourseEquivalencyDecisionError, decideCourseEquivalencyRequest } from '../../services/courseEquivalencyReview'
import {
  ACADEMIC_RECORD_LIMITATION,
  EXPLANATION_FIELD_ID,
  MAX_EXPLANATION,
  UNKNOWN_DECISION_MESSAGE,
  decisionExplanationError,
  explanationLength,
  isOverride,
  type DecisionChoice,
  type DecisionReadiness,
} from '../../utils/courseEquivalencyDecision'
import { RECOMMENDATION_DISPLAY } from '../../utils/courseEquivalencyEvaluation'
import type { CourseEquivalencyReviewRecord } from '../../utils/courseEquivalencyRecord'
import { statusLabel } from '../../utils/statusLabels'
import { formatDateTime } from '../review/format'

const OPTIONS: { value: DecisionChoice; label: string }[] = [
  { value: 'approve', label: 'Approve' },
  { value: 'reject', label: 'Reject' },
]

const OUTCOME: Record<DecisionChoice, { tone: string; glyph: string; label: string }> = {
  approve: { tone: 'approve', glyph: '✓', label: 'Approved' },
  reject: { tone: 'reject', glyph: '✕', label: 'Rejected' },
}

interface DecisionPanelProps {
  record: CourseEquivalencyReviewRecord
  /** The AI evaluation's state (decisionReadiness). Advisory only: it never blocks the
   *  decision; a ready evaluation is shown and sent, so an override of it is confirmed. */
  readiness: DecisionReadiness
  /** The chosen outcome and the explanation to the student, held by the page so a suggested
   *  reason ("Use this reason") can select Reject and fill the explanation; staff can always
   *  change the outcome and edit or replace the text. */
  choice: DecisionChoice | null
  onChoiceChange: (choice: DecisionChoice) => void
  explanation: string
  onExplanationChange: (value: string) => void
  /** Tells the page whether the form is being edited (suggestions may fill it) or confirmed. */
  onStepChange: (step: 'form' | 'confirm') => void
  /** Reload the request, decision and evaluation (after a save or a refusal). */
  onChanged: () => void
}

function decider(staffId: number | null, staffName: string | null) {
  if (staffId == null) return 'Not recorded'
  return staffName ? `${staffName} (Staff ID ${staffId})` : `Staff ID ${staffId}`
}

// A finalized request: the saved decision, read-only.
function RecordedDecision({ record }: { record: CourseEquivalencyReviewRecord }) {
  const d = record.decision
  if (d) {
    const outcome = OUTCOME[d.choice]
    return (
      <div className="pcr-recorded">
        <div className="pcr-recorded__head">
          <span className="pcr-recorded__label">Recorded decision</span>
          <span className="pcr-recorded__outcome" data-tone={outcome.tone}>
            <span aria-hidden="true">{outcome.glyph}</span>
            {outcome.label}
          </span>
        </div>
        {d.explanation.trim() && <p className="pcr-recorded__note">{d.explanation}</p>}
        <span className="pcr-recorded__meta">
          {decider(d.staffId, d.staffName)} · {formatDateTime(d.date) ?? 'Date not recorded'}
        </span>
        {d.choice === 'approve' && (
          <p className="cer-limitation" role="note">
            {ACADEMIC_RECORD_LIMITATION}
          </p>
        )}
      </div>
    )
  }
  // Finalized without a decision record (e.g. by another client changing the status directly).
  const h = record.history
  return (
    <div className="rv-alert" role="status">
      <p className="rv-alert__title">This request is {statusLabel(record.request.status, record.request.type)}.</p>
      <p className="rv-alert__body">
        No decision record exists for it, so no explanation is available.
        {h ? ` Finalized ${formatDateTime(h.date) ?? 'on an unrecorded date'} by ${decider(h.staffId, null)}.` : ''}
      </p>
    </div>
  )
}

// The administrator's final decision on a Course Equivalency request: Approve or Reject (an
// explanation to the student is required for a rejection only), an override confirmation
// when the outcome differs from a current AI recommendation, then an explicit confirmation
// step. Always available while the request is In Progress: the AI evaluation is advisory and
// never blocks it. Saved only through decide_course_equivalency_request, which identifies the
// staff member from the session. DECISION ONLY: the transcript is never changed.
function DecisionPanel({
  record, readiness, choice, onChoiceChange, explanation, onExplanationChange, onStepChange, onChanged,
}: DecisionPanelProps) {
  // The override confirmation belongs to the outcome it was given for: any change of outcome
  // (including one made by "Use this reason") asks for it again.
  const [overrideConfirmedFor, setOverrideConfirmedFor] = useState<DecisionChoice | null>(null)
  const overrideConfirmed = choice !== null && overrideConfirmedFor === choice
  const [step, setStepState] = useState<'form' | 'confirm'>('form')
  const setStep = (next: 'form' | 'confirm') => {
    setStepState(next)
    onStepChange(next)
  }
  // The evaluation shown when moving to the confirmation step (null: none usable). Sent with
  // the decision, so a change meanwhile is refused (evaluation_changed) instead of an override
  // being judged against something the administrator did not see.
  const [reviewedRunId, setReviewedRunId] = useState<number | null>(null)
  const [attempted, setAttempted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // Guards against a second submission before React re-renders.
  const savingRef = useRef(false)

  const { request, student } = record
  const finalized = request.status !== 'In Progress'
  const recommendation = readiness.ready ? readiness.recommendation : null
  const override = isOverride(choice, recommendation)
  const needsExplanation = choice === 'reject'
  const length = explanationLength(explanation)
  const choiceError = attempted && !choice ? 'Choose Approve or Reject.' : null
  const noteError = decisionExplanationError(choice, explanation, attempted)
  const overrideError =
    attempted && override && !overrideConfirmed ? 'Confirm that you are overriding the agent’s recommendation.' : null
  const studentName = student?.name ?? 'The student'
  // Only a rejection sends its explanation; an approval sends none.
  const sentExplanation = needsExplanation ? explanation.trim() : ''

  const review = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAttempted(true)
    setError(null)
    if (!choice || decisionExplanationError(choice, explanation, true) !== null) return
    if (override && !overrideConfirmed) return
    setReviewedRunId(readiness.ready ? readiness.run.id : null)
    setStep('confirm')
  }

  const save = async () => {
    if (!choice || savingRef.current) return
    savingRef.current = true
    setSaving(true)
    setError(null)
    try {
      const confirmOverride = reviewedRunId != null && override && overrideConfirmed
      const result = await decideCourseEquivalencyRequest(request.id, choice, sentExplanation, reviewedRunId, confirmOverride)
      setNotice(
        // The decision record was just saved, so an approval reads "Approved".
        `Decision saved: ${statusLabel(result.status || (choice === 'approve' ? 'Completed' : 'Rejected'), request.type, choice === 'approve')}` +
          `${result.override ? ' (override of the agent’s recommendation)' : ''}. ${studentName} has been notified.` +
          (choice === 'approve' ? ' The transcript was not changed.' : ''),
      )
    } catch (caught) {
      setError(caught instanceof CourseEquivalencyDecisionError ? caught.message : UNKNOWN_DECISION_MESSAGE)
      setStep('form')
    } finally {
      savingRef.current = false
      setSaving(false)
      // Show the real state either way: the saved decision, or the request still In
      // Progress (with a possibly newer evaluation) after a refusal.
      onChanged()
    }
  }

  return (
    <section className="pcr-decision cer-decision" aria-labelledby="cer-decision-title">
      <div className="pcr-decision__head">
        <h2 id="cer-decision-title" className="pcr-decision__title">
          Administrator decision
        </h2>
      </div>

      <div className="pcr-decision__body">
        {notice && (
          <p className="rv-saved" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p className="rv-notice" role="alert">
            {error}
          </p>
        )}

        {finalized ? (
          <RecordedDecision record={record} />
        ) : !record.details ? (
          <p className="rv-notice" role="alert">
            This request has no Course Equivalency details (old and new course), so it cannot be decided here.
          </p>
        ) : step === 'form' ? (
          <form className="pcr-decision__fields" onSubmit={review} noValidate>
            {/* The recommendation itself is shown in the AI Agent Evaluation section only. */}
            {!readiness.ready && (
              <p className="rv-muted cer-agent__none" role="note">
                {readiness.message ?? 'Loading the AI evaluation… You can decide without it.'}
              </p>
            )}

            <fieldset className="pcr-outcome" aria-describedby={choiceError ? 'cer-outcome-error' : undefined}>
              <legend className="pcr-decision__label">
                Outcome <span className="pcr-required" aria-hidden="true">*</span>
                <span className="student-visually-hidden">(required)</span>
              </legend>
              <div className="pcr-outcome__options">
                {OPTIONS.map((option) => (
                  <label key={option.value} className="pcr-outcome__option" data-checked={choice === option.value}>
                    <input
                      type="radio"
                      name="cer-outcome"
                      value={option.value}
                      checked={choice === option.value}
                      onChange={() => {
                        onChoiceChange(option.value)
                        setError(null)
                      }}
                    />
                    <span className="pcr-outcome__text">
                      <span className="pcr-outcome__label">{option.label}</span>
                    </span>
                  </label>
                ))}
              </div>
              {choiceError && (
                <span id="cer-outcome-error" className="rv-field-error">
                  ✕ {choiceError}
                </span>
              )}
            </fieldset>

            {override && recommendation && (
              <div className="pcr-disagree" role="note">
                <p className="cer-override__text">
                  Your decision differs from the agent’s recommendation ({RECOMMENDATION_DISPLAY[recommendation].label}).
                  That is allowed, but it is recorded as an override.
                </p>
                <label className="cer-override__confirm">
                  <input
                    type="checkbox"
                    checked={overrideConfirmed}
                    onChange={(event) => {
                      setOverrideConfirmedFor(event.target.checked ? choice : null)
                      setError(null)
                    }}
                    aria-invalid={overrideError ? true : undefined}
                    aria-describedby={overrideError ? 'cer-override-error' : undefined}
                  />
                  <span>I confirm that I am overriding the agent’s recommendation.</span>
                </label>
                {overrideError && (
                  <span id="cer-override-error" className="rv-field-error">
                    ✕ {overrideError}
                  </span>
                )}
              </div>
            )}
            {choice && recommendation === 'MANUAL_REVIEW' && (
              <p className="rv-muted" role="note">
                The agent did not recommend an outcome (manual review), so either decision is yours to make.
              </p>
            )}

            {needsExplanation && (
              <div className="pcr-note">
                <label htmlFor={EXPLANATION_FIELD_ID} className="pcr-decision__label">
                  Explanation to student <span className="pcr-required" aria-hidden="true">*</span>
                  <span className="student-visually-hidden">(required)</span>
                </label>
                <textarea
                  id={EXPLANATION_FIELD_ID}
                  className="pcr-note__input"
                  rows={5}
                  value={explanation}
                  required
                  onChange={(event) => {
                    onExplanationChange(event.target.value)
                    setError(null)
                  }}
                  placeholder="Explain why the request is rejected and any next steps. The student will see this."
                  aria-invalid={noteError ? true : undefined}
                  aria-describedby="cer-note-hint"
                />
                <span id="cer-note-hint" className={noteError ? 'rv-field-error' : 'pcr-note__hint'}>
                  {noteError
                    ? `✕ ${noteError}`
                    : `${length.toLocaleString('en-US')} / ${MAX_EXPLANATION.toLocaleString('en-US')} characters. Shown to the student with the outcome.`}
                </span>
              </div>
            )}

            <div className="pcr-decision__actions">
              <button type="submit" className="pcr-submit">
                Submit Final Decision
              </button>
            </div>
          </form>
        ) : (
          <div className="pcr-confirm" role="alertdialog" aria-labelledby="cer-confirm-title" aria-describedby="cer-confirm-body">
            <strong id="cer-confirm-title" className="pcr-confirm__title">
              {choice === 'approve' ? 'Approve' : 'Reject'} {request.id}?
            </strong>
            <p id="cer-confirm-body" className="pcr-confirm__body">
              This is your final administrative decision and cannot be changed afterwards. The status will change to{' '}
              {choice === 'approve' ? 'Approved' : 'Rejected'} and {studentName} will be notified
              {needsExplanation ? ' and will see your explanation' : ''}.
              {override && reviewedRunId != null ? ' It will be recorded as an override of the agent’s recommendation.' : ''}
              {reviewedRunId == null ? ' It is recorded without an AI evaluation; any evaluation still running is stopped.' : ''}
              {choice === 'approve'
                ? ' No transcript entry, credit hours, CGPA, completed hours or program change is made.'
                : ''}
            </p>
            {needsExplanation && (
              <div className="pcr-confirm__explanation">
                <span className="req-text__label">Explanation to student</span>
                <p className="req-text__body">{sentExplanation}</p>
              </div>
            )}
            <div className="pcr-decision__actions">
              <button
                type="button"
                className="pcr-submit"
                onClick={() => void save()}
                disabled={saving}
                aria-busy={saving || undefined}
              >
                {saving ? 'Saving…' : choice === 'approve' ? 'Confirm approval' : 'Confirm rejection'}
              </button>
              <button type="button" className="req-button" onClick={() => setStep('form')} disabled={saving}>
                Go back
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

export default DecisionPanel
