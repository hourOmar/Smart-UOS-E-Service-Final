// Deterministic, display-only shortening of the Raise Capacity agents' saved
// explanations (Prioritization Agent and Eligibility Agent). Nothing here calls
// a model, rewrites a fact or changes what is stored: it only
//   1. replaces raw field flags ("checks.prerequisite.verified is true") with the
//      plain words they stand for,
//   2. picks whole sentences of the original text to show first, always keeping
//      every sentence that states uncertainty, a conflict or missing data, and
//   3. leaves out sentences whose facts the card already shows.
// When anything was left out or reworded, the caller offers the original text
// ("Show full explanation"), so no saved content becomes unreachable.

/** Sentences that state uncertainty, conflict, missing data or a reason for manual review: never hidden. */
const MUST_KEEP =
  /\b(unresolved|unverif\w*|not verified|could not|cannot|can't|unable|missing|not recorded|unknown|unclear|uncertain\w*|ambiguous|conflict\w*|contradict\w*|inconsisten\w*|discrepan\w*|manual[ _]review|outside the approved|not covered|not evaluated|text condition|insufficient|incomplete|may|might|could|possibl\w*|potential\w*|unless|depends? on|not established|not confirm\w*)\b/i

const FLAG_SUBJECT: Record<string, string> = {
  prerequisite: 'the prerequisite',
  completed_hours: 'the completed-hours rule',
  capacity: 'section capacity',
}

const FLAG_WORDS: Record<string, Record<string, string>> = {
  verified: { true: 'verified', false: 'not verified', null: 'not verified' },
  satisfied: { true: 'met', false: 'not met', null: 'unresolved' },
  applicable: { true: 'applies', false: 'does not apply', null: 'applicability unknown' },
}

function flagPhrase(group: string | undefined, field: string, value: string): string {
  const f = field.toLowerCase()
  const v = value.toLowerCase()
  const subject = group ? FLAG_SUBJECT[group.toLowerCase()] : null
  if (group?.toLowerCase() === 'capacity' && f === 'satisfied') {
    return v === 'true'
      ? 'additional section capacity is available'
      : v === 'false'
        ? 'no additional section capacity is available'
        : 'section capacity is unresolved'
  }
  const word = FLAG_WORDS[f][v]
  if (!subject) return word
  return f === 'applicable' ? `${subject} ${word}` : `${subject} is ${word}`
}

const FLAG = String.raw`(?:checks\.)?(?:(prerequisite|completed_hours|capacity)\.)?(verified|satisfied|applicable)\s*(?:==|=|:|\bis\b)\s*(true|false|null)\b`

/** Plain words for raw evidence flags and field paths. Meaning is unchanged. */
export function cleanTechnicalWording(text: string, { dropFlagParentheticals = true } = {}): string {
  const dropped = dropFlagParentheticals
    ? // A parenthetical that only lists flags repeats the status badge: drop it.
      text.replace(new RegExp(String.raw`\s*\((?:\s*${FLAG}\s*(?:[,;]|\band\b)?\s*)+\)`, 'gi'), '')
    : text
  return (
    dropped
      .replace(new RegExp(FLAG, 'gi'), (_m, group: string | undefined, field: string, value: string) =>
        flagPhrase(group, field, value),
      )
      // Remaining evidence paths and field names: "checks.capacity.remaining_raise_capacity" -> "remaining raise capacity".
      .replace(/\bchecks\.(?:[a-z]+(?:_[a-z]+)*\.)?([a-z]+(?:_[a-z]+)*)\b/g, (_m, field: string) => field.replace(/_/g, ' '))
      .replace(/(?<![\w/.:-])([a-z]+(?:_[a-z]+)+)(?![\w/-])/g, (_m, field: string) => field.replace(/_/g, ' '))
      // Python-style ID lists: "[1501211, 1501215]" -> "1501211, 1501215".
      .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, '$1')
      .replace(/\[\s*\]/g, 'none')
      .replace(/^([a-z])/, (c) => c.toUpperCase())
  )
}

/** The whole saved text, as stored, with raw field flags in plain words ('' when none).
 *  Nothing is left out: every sentence and parenthetical stays. */
export function savedText(text: string | null | undefined): string {
  const full = (text ?? '').trim()
  return full ? cleanTechnicalWording(full, { dropFlagParentheticals: false }) : ''
}

const ABBREVIATION = /\b(?:e\.g|i\.e|etc|vs|approx|no|dr|mr|ms|st)\.$/i

/** Splits text into sentences (and lines); each keeps its own punctuation. */
export function splitSentences(text: string): string[] {
  const out: string[] = []
  for (const line of text.split(/\n+/)) {
    let start = 0
    const re = /[.!?](?=\s+["'(]?[A-Z0-9])/g
    let match: RegExpExecArray | null
    while ((match = re.exec(line))) {
      const candidate = line.slice(start, match.index + 1)
      if (ABBREVIATION.test(candidate)) continue
      out.push(candidate.trim())
      start = match.index + 1
    }
    out.push(line.slice(start).trim())
  }
  return out.filter((s) => s !== '')
}

// Negations ("not", "no") are deliberately NOT ignored: a sentence that says
// "not met" is only left out if the card also says so.
const STOP = new Set(
  ('the and for are was were been this that these those its with from has have had there their they which who ' +
    'therefore thus also than then into over under per one each any all student course section request').split(' '),
)

const NEGATIONS = new Set(['not', 'no', 'never', 'none', 'without', 'neither', 'nor', "isn't", "doesn't", "wasn't", 'lacks'])

const contentWords = (text: string) =>
  (text.toLowerCase().match(/[a-z][a-z'-]+/g) ?? []).map((w) => w.replace(/-/g, '')).filter((w) => w.length > 1 && !STOP.has(w))

/** Numbers (counts, course IDs, terms) and letter grades: the facts a sentence states. */
const factTokens = (text: string) => [
  ...(text.match(/\d+(?:\.\d+)?/g) ?? []),
  ...(text.match(/(?<![\w'])(?:[A-F][+-]?|W|IP)(?![\w'])/g) ?? []),
]

/** True when the sentence states nothing the card does not already show. */
export function repeatsShownFacts(sentence: string, shown: string): boolean {
  if (MUST_KEEP.test(sentence)) return false
  const tokens = factTokens(sentence)
  const own = contentWords(sentence)
  if (own.length === 0 && tokens.length === 0) return false
  const shownTokens = new Set(factTokens(shown))
  if (!tokens.every((t) => shownTokens.has(t))) return false
  const shownWords = new Set(contentWords(shown))
  // A negation the card does not also state may contradict it ("not available"): keep the sentence.
  if (own.some((w) => NEGATIONS.has(w) && !shownWords.has(w))) return false
  // With facts that all appear in the card, the words only need to be mostly the card's.
  const overlap = own.length === 0 ? 1 : own.filter((w) => shownWords.has(w)).length / own.length
  return overlap >= (tokens.length > 0 ? 0.5 : 0.75)
}

export interface CompactText {
  /** What to show by default. Empty when the card already shows everything. */
  short: string
  /** The saved text, unchanged. */
  full: string
  /** True when `short` leaves something out or rewords a flag: offer the full text. */
  shortened: boolean
}

interface CompactOptions {
  /** Sentences to show by default (sentences stating uncertainty are always shown, even beyond this). */
  maxSentences: number
  /** Text the card already shows; sentences that only repeat it are left out. */
  shownFacts?: string
}

/** Picks the sentences to show first. Pure and deterministic. */
export function compactExplanation(text: string | null | undefined, { maxSentences, shownFacts }: CompactOptions): CompactText {
  const full = (text ?? '').trim()
  if (!full) return { short: '', full: '', shortened: false }
  const sentences = splitSentences(cleanTechnicalWording(full))
  const keep = sentences.map((s) => MUST_KEEP.test(s))
  const redundant = sentences.map((s, i) => !keep[i] && shownFacts !== undefined && repeatsShownFacts(s, shownFacts))
  const chosen = new Set<number>()
  // The opening sentence (usually the conclusion) and every uncertainty / conflict sentence.
  const first = redundant.indexOf(false)
  if (first > -1) chosen.add(first)
  keep.forEach((k, i) => k && chosen.add(i))
  // Then the next sentences, in order, up to the limit.
  for (let i = 0; i < sentences.length && chosen.size < maxSentences; i++) if (!redundant[i]) chosen.add(i)
  const short = sentences.filter((_s, i) => chosen.has(i)).join(' ')
  return { short, full, shortened: chosen.size < sentences.length || cleanTechnicalWording(full) !== full }
}

/** Key-evidence items that no displayed factor text already states (to be shown separately). */
export function uncoveredEvidence(items: string[], factorTexts: string[]): string[] {
  const shown = factorTexts.join(' ')
  return items.filter((item) => item.trim() !== '' && !repeatsShownFacts(item, shown))
}
