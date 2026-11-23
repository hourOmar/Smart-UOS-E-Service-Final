import { useId, useState, type ReactNode } from 'react'
import type { CompactText as Compact } from '../../utils/raiseCapacityExplanations'

interface CompactTextProps {
  text: Compact
  className?: string
  /** Shown before the text, e.g. "Agent’s explanation:". */
  label?: ReactNode
  /** Shown when every sentence repeats the card (the full text stays one click away). */
  coveredNote?: string
  moreLabel?: string
}

// An agent explanation shown shortened, with the saved text one click away
// whenever the short version leaves anything out or rewords a raw flag.
function CompactText({ text, className, label, coveredNote, moreLabel = 'Show full explanation' }: CompactTextProps) {
  const [open, setOpen] = useState(false)
  const id = useId()
  if (!text.full) return null
  const body = open ? text.full : text.short
  return (
    <div className={`rca-compact${className ? ` ${className}` : ''}`}>
      <p id={id} className="rca-compact__text">
        {label}
        {label ? ' ' : null}
        {body || <span className="rca-compact__covered">{coveredNote ?? 'Already shown above.'}</span>}
      </p>
      {text.shortened && (
        <button
          type="button"
          className="rca-compact__toggle"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? 'Show less' : moreLabel}
        </button>
      )}
    </div>
  )
}

export default CompactText
