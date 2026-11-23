import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../services/backendApi'
import { fetchPriorities, rerunPriority, retryPriority, type PriorityState } from '../services/raiseCapacityPriority'

// While a check is running (started here or elsewhere), the state is re-read this often...
const POLL_MS = 4000
// ...for at most this many times (about ten minutes, the backend's run timeout).
const MAX_POLLS = 150

type Status = 'loading' | 'ready' | 'error'

interface State {
  forKey: string
  status: Status
  data: PriorityState | null
  error: string | null
  /** This page's own request to start a check is in flight. */
  running: boolean
  /** A problem with the latest action, shown without hiding the saved result. */
  notice: string | null
}

const messageOf = (error: unknown) =>
  error instanceof ApiError ? error.message : 'The priority service could not be reached.'

/** A check is in progress: a first check, a retry, or a re-evaluation of a saved priority. */
export const priorityCheckActive = (data: PriorityState | null) =>
  data?.state === 'running' || data?.last_run?.status === 'running'

/** What Re-evaluate does for this state: re-evaluate a saved priority, retry after
 *  a failed check, or nothing (the backend decides again under its own lock). */
export const priorityAction = (data: PriorityState | null) =>
  data?.can_rerun ? rerunPriority : data?.can_retry ? retryPriority : null

// The priority of ONE Raise Capacity request, for its review page. It reads the
// same staff endpoint as the requests table (so both show the same saved
// result) and never starts a first check (the request lists do that). Staff can
// re-evaluate a saved priority, or retry after a failed check, with rerun().
// While any check runs the saved result stays on screen and the state is
// re-read until it finishes. A read failure is reported as such, never as
// "no priority".
function useRaiseCapacityPriority(requestId: string | undefined) {
  const [attempt, setAttempt] = useState(0)
  const key = requestId ? `${requestId}#${attempt}` : ''
  const [state, setState] = useState<State | null>(null)
  const startRef = useRef<((data: PriorityState | null) => Promise<void>) | null>(null)

  useEffect(() => {
    if (!requestId) return
    let cancelled = false
    let timer: number | undefined

    const update = (patch: Partial<State> | ((prev: State) => Partial<State>)) => {
      if (cancelled) return
      setState((prev) => {
        const base: State =
          prev && prev.forKey === key
            ? prev
            : { forKey: key, status: 'loading', data: null, error: null, running: false, notice: null }
        return { ...base, ...(typeof patch === 'function' ? patch(base) : patch) }
      })
    }

    const poll = (count: number) => {
      window.clearTimeout(timer)
      if (count >= MAX_POLLS) {
        update({ notice: 'The priority check is taking longer than expected. Reload the page later.' })
        return
      }
      timer = window.setTimeout(() => void load(count + 1), POLL_MS)
    }

    const load = async (count: number) => {
      try {
        const [found] = await fetchPriorities([requestId])
        if (cancelled) return
        update({ status: 'ready', data: found ?? null, error: null })
        if (priorityCheckActive(found ?? null)) poll(count)
      } catch (error) {
        if (cancelled) return
        // Keep a result already on screen; report the problem beside it.
        update((prev) =>
          prev.data ? { notice: messageOf(error) } : { status: 'error', data: null, error: messageOf(error) },
        )
      }
    }

    const start = async (data: PriorityState | null) => {
      const action = priorityAction(data)
      if (!action) return
      update({ running: true, notice: null })
      try {
        const next = await action(requestId)
        if (cancelled) return
        update({ status: 'ready', data: next, error: null, running: false })
        if (priorityCheckActive(next)) poll(0)
      } catch (error) {
        if (cancelled) return
        // The saved result stays on screen; the problem is shown beside it.
        update({ running: false, notice: messageOf(error) })
        // Refused because the state changed elsewhere: show the current state.
        if (error instanceof ApiError && error.status === 409) void load(0)
      }
    }

    startRef.current = start
    void load(0)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [requestId, key])

  const current = state && state.forKey === key ? state : null
  const data = current?.data ?? null

  const retry = useCallback(() => setAttempt((count) => count + 1), [])
  const rerun = useCallback(() => {
    void startRef.current?.(data)
  }, [data])

  return {
    status: current?.status ?? ('loading' as Status),
    data,
    error: current?.error ?? null,
    running: current?.running ?? false,
    notice: current?.notice ?? null,
    /** Reloads the saved state after a read failure ("Try again"). */
    retry,
    /** Re-evaluates a saved priority, or retries after a failed check. */
    rerun,
  }
}

export type RaiseCapacityPriority = ReturnType<typeof useRaiseCapacityPriority>
export default useRaiseCapacityPriority
