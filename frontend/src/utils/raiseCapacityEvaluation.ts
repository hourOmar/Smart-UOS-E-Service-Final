// Display helpers for the Raise Capacity Eligibility Agent's stored runs (pure
// presentation logic: nothing here calls the backend, a model or the database).
import type {
  CheckStatus,
  EvaluationRun,
  RequirementCondition,
  SuggestionTone,
} from '../services/raiseCapacityReview'

export const TONE_LABELS: Record<SuggestionTone, string> = {
  formal: 'Formal',
  concise: 'Concise',
  supportive: 'Supportive',
}

const TONES: SuggestionTone[] = ['formal', 'concise', 'supportive']

export interface RejectionSuggestionsView {
  reasons: { tone: SuggestionTone; label: string; text: string }[]
  /** Labels of the confirmed failures the suggestions explain. */
  verifiedReasons: string[]
  conflictNote: string | null
  message: string | null
}

/** The suggested rejection explanations — only for a successful (completed,
 *  Gemini-decided) REJECT evaluation; null otherwise. */
export function rejectionSuggestions(run: EvaluationRun | null | undefined): RejectionSuggestionsView | null {
  if (!run || run.run_status !== 'completed' || run.gemini_status !== 'ok' || run.recommendation !== 'REJECT') {
    return null
  }
  const r = run.rejection_explanation
  if (!r) {
    return {
      reasons: [],
      verifiedReasons: [],
      conflictNote: null,
      message: 'No suggested explanations were recorded for this evaluation. Write the explanation yourself.',
    }
  }
  const stored = Array.isArray(r.suggested_reasons) ? r.suggested_reasons : []
  const reasons = TONES.flatMap((tone) => {
    const found = stored.find((s) => s?.tone === tone && typeof s.text === 'string' && s.text.trim() !== '')
    return found ? [{ tone, label: TONE_LABELS[tone], text: found.text.trim() }] : []
  })
  const message =
    reasons.length === 0
      ? 'No suggested explanation could be prepared. Write the explanation yourself.'
      : r.status === 'fallback'
        ? 'These suggestions were built only from the verified failures.'
        : null
  return {
    reasons,
    verifiedReasons: (Array.isArray(r.keywords) ? r.keywords : []).map((k) => k.label).filter(Boolean),
    conflictNote: r.conflict_note?.trim() ? r.conflict_note.trim() : null,
    message,
  }
}

/** True for evidence recorded by agent 2.0.0 or later (the complete requirement). */
export function hasRequirementEvidence(run: EvaluationRun): boolean {
  return Boolean(run.evidence?.academic_requirement)
}

export type Tone = 'pass' | 'fail' | 'unknown'

/** The card colour and label for a 2.0.0 check status (statuses exactly as recorded). */
export function checkDisplay(status: CheckStatus | string | null | undefined): { tone: Tone; label: string } {
  switch (status) {
    case 'SATISFIED':
      return { tone: 'pass', label: 'PASSED' }
    case 'NOT_SATISFIED':
      return { tone: 'fail', label: 'FAILED' }
    case 'NOT_APPLICABLE':
      return { tone: 'unknown', label: 'NOT APPLICABLE' }
    case 'NOT_EVALUATED':
      return { tone: 'unknown', label: 'NOT EVALUATED' }
    case 'CONFLICT':
      return { tone: 'unknown', label: 'CONFLICTING' }
    default:
      return { tone: 'unknown', label: 'UNRESOLVED' }
  }
}

const MODE_NOTE: Record<string, string> = {
  PRE: '',
  PRE_OR_CO: ' (completed before, or taken in the same term)',
  CO: ' (taken in the same term)',
}

const CONDITION_STATUS: Record<RequirementCondition['status'], { label: string; tone: Tone }> = {
  SATISFIED: { label: 'Met', tone: 'pass' },
  NOT_SATISFIED: { label: 'Not met', tone: 'fail' },
  UNRESOLVED: { label: 'Unresolved', tone: 'unknown' },
}

/** One evaluated course condition: the course, how it may be met, and its recorded status. */
export function courseCondition(condition: RequirementCondition, label: (id: string) => string) {
  return {
    text: `${label(condition.course_id ?? '')}${MODE_NOTE[condition.mode ?? 'PRE'] ?? ''}`,
    status: CONDITION_STATUS[condition.status] ?? CONDITION_STATUS.UNRESOLVED,
    reason: condition.reason,
  }
}

/** One evaluated standing condition: the standing and its threshold. */
export function standingCondition(condition: RequirementCondition) {
  const threshold = condition.required_earned_credits
  return {
    text: `${condition.standing_text ?? 'Academic standing'}${threshold != null ? ` (at least ${threshold} completed credit hours)` : ''}`,
    status: CONDITION_STATUS[condition.status] ?? CONDITION_STATUS.UNRESOLVED,
    reason: condition.reason,
  }
}
