import { SUPABASE_ANON_KEY, SUPABASE_STORAGE_KEY, SUPABASE_URL, API_BASE_URL } from './env'
import { passwordFor } from './credentials'
import type { Account } from './accounts'

/**
 * Mints a REAL Supabase session per role and shapes it into a Playwright `storageState` file.
 *
 * ## Why this works -- verified in the pinned client's source, not assumed
 *
 * The app never reads a token from anywhere but supabase-js:
 * `frontend/src/core/http/api.ts:38-51` builds every request's `Authorization` header from
 * `getSession()`, which is `supabase.auth.getSession()` (`core/auth/supabase.ts:41-45`).
 *
 * So the whole seam is "make `getSession()` return a real session", and in
 * `@supabase/auth-js@2.112.2` that is a plain localStorage read:
 *
 *   - persistence is `await storage.setItem(key, JSON.stringify(data))`
 *     (`auth-js/src/lib/helpers.ts:129-135`) -- plain JSON, **no** base64 prefix and **no**
 *     chunking (chunking is an `@supabase/ssr` cookie concern, not the localStorage path);
 *   - `getSession()` reads that key back and accepts it if `_isValidSession` passes, which
 *     requires exactly `access_token`, `refresh_token` and `expires_at`
 *     (`auth-js/src/GoTrueClient.ts:4786-4795`), then returns it unless `expires_at` is within
 *     the expiry margin (`GoTrueClient.ts:3044-3053`).
 *
 * The password-grant response supplies all three fields. Confirmed empirically against the live
 * project on 2026-09-01: `POST /auth/v1/token?grant_type=password` -> 200 with keys
 * `access_token, expires_at, expires_in, refresh_token, token_type, user, weak_password`
 * (`expires_in` 3600). So the session object is written through verbatim -- nothing is synthesised.
 *
 * ## Why not drive the sign-in form instead
 *
 * Because it does not authenticate. `frontend/src/App.tsx:218-221`:
 *
 *     function SignInRoute() {
 *       const navigate = useNavigate()
 *       return <SignIn onSubmit={() => navigate('/planner')} />
 *     }
 *
 * -- the #52 fixture seam. `onSubmit` navigates and never calls `signIn()`, so a form-driven login
 * would produce a context with NO session, and every surface's API call would 401. Injection is not
 * a shortcut around a working login here; it is the only way to get an authenticated context at all
 * until #52 lands.
 */

export type MintedSession = {
  access_token: string
  refresh_token: string
  expires_at: number
  expires_in: number
  token_type: string
  user?: unknown
}

export type StorageState = {
  cookies: never[]
  origins: Array<{ origin: string; localStorage: Array<{ name: string; value: string }> }>
}

export async function mintSession(account: Account): Promise<MintedSession> {
  const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: 'POST',
    headers: { apikey: SUPABASE_ANON_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: account.email, password: passwordFor(account.bucket) }),
  })
  if (!res.ok) {
    let code = ''
    try {
      const body = (await res.json()) as { error_code?: string; error?: string }
      code = body.error_code ?? body.error ?? ''
    } catch {
      /* non-JSON body; the status is the useful part */
    }
    // The email is a non-secret identifier from the committed cast; the password never appears.
    throw new Error(
      `E6.2 setup: password grant failed for ${account.key} (${account.email}): ` +
        `HTTP ${res.status}${code ? ` ${code}` : ''}.`,
    )
  }
  const session = (await res.json()) as MintedSession
  if (!session.access_token || !session.refresh_token || typeof session.expires_at !== 'number') {
    throw new Error(
      `E6.2 setup: token response for ${account.key} is missing one of ` +
        `access_token/refresh_token/expires_at, which @supabase/auth-js's _isValidSession requires.`,
    )
  }
  return session
}

/**
 * Wraps a minted session in the exact `storageState` shape Playwright 1.62.1 accepts.
 *
 * Schema taken from the installed types
 * (`node_modules/playwright-core/types/types.d.ts:10483-10494`):
 * `{ cookies: [...], origins: [{ origin, localStorage: [{ name, value }] }] }`.
 *
 * `origin` must be the app's origin (the vite dev server), not Supabase's -- localStorage is
 * partitioned by origin and the app reads its own.
 */
export function toStorageState(session: MintedSession, appOrigin: string): StorageState {
  return {
    cookies: [],
    origins: [
      {
        origin: new URL(appOrigin).origin,
        localStorage: [{ name: SUPABASE_STORAGE_KEY, value: JSON.stringify(session) }],
      },
    ],
  }
}

/** Decodes a JWT payload without verifying it -- used only to read `sub` for the isolation proof. */
export function jwtClaims(accessToken: string): Record<string, unknown> {
  const payload = accessToken.split('.')[1]
  return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as Record<string, unknown>
}

/** Calls the real backend as this token's owner. Used to prove server-side identity, not to mock it. */
export async function authMe(
  accessToken: string,
): Promise<{ status: number; userId?: string; roleName?: string; facilityId?: string | null }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!res.ok) return { status: res.status }
  const body = (await res.json()) as {
    data?: { user_id?: string; role_name?: string; facility_id?: string | null }
  }
  return {
    status: res.status,
    userId: body.data?.user_id,
    roleName: body.data?.role_name,
    facilityId: body.data?.facility_id ?? null,
  }
}
