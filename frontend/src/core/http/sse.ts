import { getSession } from '@/core/auth/supabase'
import { apiErrorFromResponse, readEnvelope, unauthenticatedError } from './errors'
import { notifyUnauthorized } from './unauthorized'

/**
 * SSE client for `POST /api/v1/chat/stream`.
 *
 * **The one deliberate `fetch` outside `core/http/api.ts`** -- and it follows that file's
 * interceptor contract to the letter rather than being an exemption from it:
 *
 *  - the token is read from `getSession()` **here, at connect time**, not passed in by the caller.
 *    Before 2026-09-01 `features/driver/lib/use-driver-turn.ts` did its own `getSession()` and
 *    handed the raw string in, which is per-call-site plumbing of exactly the kind the contract
 *    exists to prevent -- and it meant the driver surface, alone in the app, could open a stream
 *    with a token nothing else had validated.
 *  - a **401 funnels into the same central handler** (`notifyUnauthorized`), both on the initial
 *    response and on an in-stream `error` frame carrying `status_code: 401`. The stream is the one
 *    place a token can die *after* the request succeeded, since a turn can outlive its own token's
 *    expiry margin, so the frame check is not redundant with the response check.
 *  - failures throw the same `ApiError` every other call throws, so `err.code` branching works
 *    identically here.
 *
 * **Why this is not `EventSource`.** TECH_STACK.md section 9 picks SSE over WebSocket and
 * notes native `EventSource` support as part of the rationale -- but the endpoint we actually
 * have is a **POST** carrying a Supabase bearer token, and `EventSource`'s constructor takes
 * only `(url, { withCredentials })`: no method, no headers.  Verified against MDN rather
 * than assumed.  So the transport is `fetch` + a `ReadableStream` reader, which also gives
 * us `AbortSignal` for free -- and abort matters here, because a driver navigating away
 * mid-turn should not leave an inference running.
 *
 * No dependency added for this.  `@microsoft/fetch-event-source` is the usual reach, but the
 * parser below is ~40 lines against a stream WE control the format of, and at this product's
 * scale a supply-chain edge for that is the wrong trade.
 *
 * Frame contract, read off backend/app/assistant/run_assistant.py and
 * backend/app/api/v1/routers/chat.py (not guessed):
 *   event: start   data: { thread_id, session_id }
 *   event: token   data: { content }
 *   event: status  data: { tool }
 *   event: error   data: { code, message, status_code? }
 *   event: done    data: <the full turn result>
 */

export type ChatStreamEvent =
  | { event: 'start'; data: { thread_id: string; session_id: string } }
  | { event: 'token'; data: { content: string } }
  | { event: 'status'; data: { tool: string } }
  | { event: 'error'; data: { code: string; message: string; status_code?: number } }
  | { event: 'done'; data: Record<string, unknown> }

export type SseFrame = { event: string; data: unknown }

/** Parses the SSE wire format into frames.  Handles multi-line `data:` and the blank-line
 *  frame terminator; ignores comment lines (`:` keepalives) and unknown fields, per the
 *  spec's own "ignore what you do not understand" rule. */
export function createSseParser(onFrame: (frame: SseFrame) => void) {
  let buffer = ''

  const flushBlock = (block: string) => {
    let eventName = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line === '' || line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon === -1 ? line : line.slice(0, colon)
      // A single leading space after the colon is part of the format, not the value.
      const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
      if (field === 'event') eventName = value
      else if (field === 'data') dataLines.push(value)
    }
    if (dataLines.length === 0) return
    const raw = dataLines.join('\n')
    let data: unknown = raw
    try {
      data = JSON.parse(raw)
    } catch {
      /* a non-JSON payload is still a frame; hand it over as the raw string */
    }
    onFrame({ event: eventName, data })
  }

  return {
    push(chunk: string) {
      buffer += chunk
      let idx: number
      // Frames are separated by a blank line.  Accept \n\n and \r\n\r\n.
      while ((idx = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const match = /\r?\n\r?\n/.exec(buffer.slice(idx))!
        const block = buffer.slice(0, idx)
        buffer = buffer.slice(idx + match[0].length)
        flushBlock(block)
      }
    },
    /** Called once the body ends, in case the server omitted a trailing blank line. */
    end() {
      if (buffer.trim()) {
        flushBlock(buffer)
        buffer = ''
      }
    },
  }
}

export type ChatStreamRequest = {
  url: string
  body: unknown
  signal?: AbortSignal
}

/** Async generator over the turn's frames.  Consumers `for await` it. */
export async function* streamChat(req: ChatStreamRequest): AsyncGenerator<SseFrame> {
  // Contract rule 1/2: read the token at send time, from supabase-js, so `autoRefreshToken` is
  // what keeps a long-lived driver session alive rather than anything in this file.
  const session = await getSession()
  if (!session?.access_token) throw unauthenticatedError()

  const res = await fetch(req.url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify(req.body),
    signal: req.signal,
  })

  if (!res.ok || !res.body) {
    // Rule 3: 401 is central. Everything else is the caller's to render.
    if (res.status === 401) notifyUnauthorized()
    throw apiErrorFromResponse(res, await readEnvelope<unknown>(res))
  }

  const queue: SseFrame[] = []
  const parser = createSseParser((f) => queue.push(f))
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (value) parser.push(value)
      if (done) {
        parser.end()
        while (queue.length) yield inspect(queue.shift()!)
        return
      }
      while (queue.length) yield inspect(queue.shift()!)
    }
  } finally {
    reader.releaseLock()
  }
}

/**
 * Rule 3, applied to the in-stream failure path.
 *
 * `backend/app/api/v1/routers/chat.py` emits `event: error` with `{ code, message, status_code }`
 * for a failure that happens *after* the response headers are already out -- which is where a
 * token expiring mid-turn shows up, since the HTTP status was 200 by then. Routing it through the
 * same handler means a driver whose session died mid-conversation gets the same one sign-out path
 * as everyone else, instead of a "Turn failed" bubble and a surface that silently stops working.
 *
 * Pass-through: the frame is returned unchanged so the caller still renders its own error state.
 */
function inspect(frame: SseFrame): SseFrame {
  if (frame.event === 'error') {
    const data = frame.data as { status_code?: number } | null
    if (data?.status_code === 401) notifyUnauthorized()
  }
  return frame
}
