import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import * as Sentry from '@sentry/react'

import App from './App.tsx'
import { isApiError } from './core/http/errors.ts'
import { AppProviders } from './providers.tsx'
import './styles/theme.css'

/*
 * E7.2 (issue #46) — Sentry, DSN-gated.
 *
 * `DEPLOYMENT.md` §8 (D-3) gives Sentry exactly one job on both sides: unhandled exceptions with
 * stack traces. CloudWatch already owns rates and infrastructure signals; LangSmith already owns
 * what happens inside an LLM turn. Errors-only is therefore the design, not a saving, and three
 * consequences follow that are each easy to get wrong.
 *
 * ## 1. A *static* import, even though this ships dark
 *
 * The obvious shape for an optional dependency is `await import('@sentry/react')` inside the `if`.
 * It is the wrong one here, and the build proves it rather than the intuition:
 *
 *   | variant                              | JS gzip total | PWA precache |
 *   |--------------------------------------|---------------|--------------|
 *   | no Sentry at all                     |    314.76 KiB |  1182.77 KiB |
 *   | dynamic `import()`, no DSN           |    489.42 KiB |  1663.51 KiB |
 *   | static import, no DSN  (this file)   |    315.92 KiB |  1185.70 KiB |
 *   | static import, DSN set at build time |    342.21 KiB |  1266.17 KiB |
 *
 * `VITE_*` variables are **inlined at build time**, not read at runtime (`DEPLOYMENT.md` §5 — the
 * same property that made the owner redeploy Vercel before `VITE_API_BASE_URL` took effect). So
 * with no DSN configured, `sentryDsn` folds to `''`, this whole branch becomes dead code, and
 * Rolldown deletes the SDK outright: +1.16 KiB gzip, which is as dark as dark gets.
 *
 * A dynamic import cannot be eliminated that way — the chunk is emitted whether or not the branch
 * is reachable, the namespace object is opaque so nothing inside it tree-shakes (Session Replay
 * and rrweb were verified present in that chunk), and `vite-plugin-pwa`'s `globPatterns` then
 * **precaches** it. That is +480 KiB pushed onto the cheap Android device `TECH_STACK.md` §9 names
 * as the whole reason the driver surface is a PWA, in exchange for a feature that is switched off.
 *
 * The tradeoff, stated plainly: turning Sentry on is a rebuild, not an env-var flip. That is
 * already true of every `VITE_*` var on this project, so it costs nothing new.
 *
 * ## 2. No `integrations` array is passed
 *
 * `integrations: []` would read as "keep it minimal" and would in fact *replace* the browser
 * defaults — including `globalHandlers`, the `window.onerror`/`unhandledrejection` hook that is the
 * entire reason to install this. Omitting the key keeps the defaults.
 * `browserTracingIntegration` and `replayIntegration` are **not** among them and must be opted
 * into, which we deliberately do not do: Session Replay records the driver's screen, which is a
 * data-residency decision before it is a bundle one.
 *
 * ## 3. `tracesSampleRate: 0`
 *
 * Performance tracing belongs to LangSmith per D-3. Zero keeps the transport idle instead of
 * sampling transactions nobody reads.
 */
const sentryDsn = String(import.meta.env.VITE_SENTRY_DSN ?? '').trim()

if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: String(import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE),
    release: String(import.meta.env.VITE_SENTRY_RELEASE ?? '') || undefined,
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend(event, hint) {
      const cause = hint?.originalException
      if (!isApiError(cause)) return event
      /*
       * An `ApiError` is the server *refusing on purpose* — `FORBIDDEN` on an out-of-scope read,
       * `SNAPSHOT_STALE` on a raced confirm, `UNAUTHENTICATED` before the request even leaves the
       * browser. Every one of those already renders its own screen (`core/http/errors.ts` exists
       * precisely so the code can be branched on). Reporting them as crashes would bury the
       * unhandled `TypeError` this integration exists to surface under thousands of events that
       * are the product working correctly.
       *
       * 5xx is the exception: the server genuinely broke. The backend's own Sentry event for the
       * same failure carries the same `request_id`, so tagging it here is what lets one click join
       * the browser stack trace to the server stack trace.
       */
      if (cause.status < 500) return null
      event.tags = {
        ...event.tags,
        api_error_code: cause.code,
        ...(cause.requestId ? { request_id: cause.requestId } : {}),
      }
      return event
    },
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AppProviders>
        <App />
      </AppProviders>
    </BrowserRouter>
  </StrictMode>,
)
