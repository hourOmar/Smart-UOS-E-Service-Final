// Display of the Prioritization Agent's per-factor signals (factor_signals in the
// saved result). A signal is the factor's contribution to the priority
// assessment, not an eligibility pass/fail. Only the four values the backend
// validates are shown as a colour; anything else (results saved before signals
// existed, a missing factor, an unknown value) is grey "Not classified".
// Nothing here looks at the explanation text or the overall priority.

export type FactorTone = 'pass' | 'fail' | 'review' | 'unknown'

export interface FactorSignalDisplay {
  /** The card colour (the check-card tones; 'review' is yellow). */
  tone: FactorTone
  glyph: string
  label: string
  /** The saved value, or null when not classified. */
  signal: 'HIGHER' | 'LOWER' | 'REVIEW' | 'NEUTRAL' | null
}

export const FACTOR_SIGNAL_DISPLAY: Record<'HIGHER' | 'LOWER' | 'REVIEW' | 'NEUTRAL', FactorSignalDisplay> = {
  HIGHER: { tone: 'pass', glyph: '↑', label: 'Raises priority', signal: 'HIGHER' },
  LOWER: { tone: 'fail', glyph: '↓', label: 'Lowers priority', signal: 'LOWER' },
  REVIEW: { tone: 'review', glyph: '!', label: 'Needs review', signal: 'REVIEW' },
  NEUTRAL: { tone: 'unknown', glyph: '–', label: 'Neutral', signal: 'NEUTRAL' },
}

export const NOT_CLASSIFIED: FactorSignalDisplay = { tone: 'unknown', glyph: '–', label: 'Not classified', signal: null }

/** The display of one factor's saved signal; "Not classified" unless it is one of the four values. */
export function factorSignalDisplay(signals: unknown, factor: string): FactorSignalDisplay {
  if (!signals || typeof signals !== 'object' || Array.isArray(signals)) return NOT_CLASSIFIED
  if (!Object.prototype.hasOwnProperty.call(signals, factor)) return NOT_CLASSIFIED
  const value = (signals as Record<string, unknown>)[factor]
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(FACTOR_SIGNAL_DISPLAY, value)
    ? FACTOR_SIGNAL_DISPLAY[value as keyof typeof FACTOR_SIGNAL_DISPLAY]
    : NOT_CLASSIFIED
}
