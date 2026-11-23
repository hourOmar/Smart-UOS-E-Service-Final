import { callBackend } from './backendApi'

// Staff-only Raise Capacity priorities from the backend (priority agent).
// Never imported by student pages.

export type PriorityLevel = 'HIGH' | 'MEDIUM' | 'LOW' | 'MANUAL_REVIEW'

/** Shared by the Priority column and the review page's Priority assessment. */
export const PRIORITY_LABELS: Record<PriorityLevel, string> = {
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  MANUAL_REVIEW: 'Manual review',
}

export type PriorityStateName =
  | 'saved'
  | 'needs_attention'
  | 'running'
  | 'failed'
  | 'not_started'
  | 'not_found'

export interface PriorityRun {
  id: number
  status: 'running' | 'completed' | 'failed' | 'discarded' | 'interrupted'
  trigger: 'automatic' | 'retry' | 'rerun'
  started_at: string
  finished_at: string | null
  error_message: string | null
  model: string | null
  agent_version: string
}

/** The agent's explanation of each factor, as saved with its result. */
export interface FactorExplanations {
  graduation: string
  degree_progress: string
  course_requirement: string
  course_availability: string
  previous_attempts: string
  prerequisite: string
  progression: string
}

/** Each factor's contribution to the priority assessment (agent 1.1.0 and later),
 *  checked against the evidence before it was saved. Not an eligibility result. */
export type FactorSignal = 'HIGHER' | 'LOWER' | 'REVIEW' | 'NEUTRAL'

/** The saved result (Raise_Capacity.Priority_Result), exactly as the agent stored it. */
export interface PriorityResult {
  request_id?: string
  priority?: PriorityLevel
  reasoning?: string
  factor_explanations?: FactorExplanations
  key_evidence?: string[]
  /** Absent in results saved before factor signals existed; read with care
   *  (anything but a known value shows as "Not classified"). */
  factor_signals?: unknown
}

export interface PriorityState {
  request_id: string
  state: PriorityStateName
  priority: PriorityLevel | null
  /** The saved result (reasoning, factor explanations, key evidence). */
  result: PriorityResult | null
  attention_reason: string | null
  request_status: string | null
  can_retry: boolean
  auto_eligible: boolean
  /** A saved priority may be re-evaluated (In Progress, no run in progress).
   *  Absent from older backends. */
  can_rerun?: boolean
  last_run: PriorityRun | null
}

const MESSAGES = {
  service: 'priority service',
  byStatus: {
    404: 'This Raise Capacity request was not found.',
    409: 'This request cannot be retried now.',
    429: 'Other priority checks are still running. Try again shortly.',
  },
}

const BASE = '/api/staff/raise-capacity'

/** Saved states only; never starts a check. */
export async function fetchPriorities(requestIds: string[]): Promise<PriorityState[]> {
  const query = new URLSearchParams(requestIds.map((id) => ['request_id', id]))
  const body = await callBackend<{ priorities: PriorityState[] }>(`${BASE}/priorities?${query}`, undefined, MESSAGES)
  return body.priorities
}

/** Starts checks for eligible requests (In Progress, nothing saved, never
 *  checked); the backend decides. Returns every request's state. */
export async function startAutomaticPriorities(requestIds: string[]): Promise<PriorityState[]> {
  const body = await callBackend<{ priorities: PriorityState[]; started: string[] }>(
    `${BASE}/priorities/automatic`,
    { method: 'POST', body: JSON.stringify({ request_ids: requestIds }) },
    MESSAGES,
  )
  return body.priorities
}

/** Manual retry after a failed or interrupted check. */
export async function retryPriority(requestId: string): Promise<PriorityState> {
  const body = await callBackend<{ priority: PriorityState }>(
    `${BASE}/${encodeURIComponent(requestId)}/priority/retry`,
    { method: 'POST' },
    MESSAGES,
  )
  return body.priority
}

const RERUN_MESSAGES = {
  service: 'priority service',
  byStatus: {
    404: 'This Raise Capacity request was not found.',
    409: 'The priority cannot be re-evaluated now: a check may already be running, or the request is no longer In Progress.',
    429: 'Other priority checks are still running. Try again shortly.',
    503: 'Priority re-evaluation is not available right now. Try again later.',
  },
}

/** Re-evaluates a saved priority (In Progress requests only). The saved
 *  priority stays in place until the new result is saved; a failed
 *  re-evaluation leaves it unchanged. Never changes the request. */
export async function rerunPriority(requestId: string): Promise<PriorityState> {
  const body = await callBackend<{ priority: PriorityState }>(
    `${BASE}/${encodeURIComponent(requestId)}/priority/rerun`,
    { method: 'POST' },
    RERUN_MESSAGES,
  )
  return body.priority
}
