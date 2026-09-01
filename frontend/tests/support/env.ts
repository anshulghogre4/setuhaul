import { readFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Minimal dotenv reader.
 *
 * The frontend has no `dotenv` dependency and this suite deliberately does not add one (see
 * `playwright.config.ts` on why no new dependency). Vite injects `.env.local` into the *browser*
 * bundle via `import.meta.env`, but Playwright's setup project runs in **Node**, where
 * `import.meta.env` does not exist -- so the same values have to be read from disk here.
 *
 * Values are returned, never logged. Nothing in this module prints.
 */

const HERE = dirname(fileURLToPath(import.meta.url))
export const FRONTEND_DIR = resolve(HERE, '../..')
export const REPO_ROOT = resolve(FRONTEND_DIR, '..')

function parseDotenv(path: string): Record<string, string> {
  if (!existsSync(path)) return {}
  const out: Record<string, string> = {}
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$/)
    if (!m) continue
    let value = m[2].trim()
    // Strip one layer of surrounding quotes if present.
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    out[m[1]] = value
  }
  return out
}

/**
 * `frontend/.env.local` first (it is what `vite dev` actually serves to the app, so the suite and
 * the app agree on which Supabase project and which API base are in play), then the repo-root
 * `.env.local` as a fallback for values the frontend file does not carry. Real process env wins
 * over both, so CI can override without editing a file.
 *
 * `.env.production.local` is deliberately NOT read -- it points at the deployed ECS backend, and
 * these suites write.
 */
const fileEnv = {
  ...parseDotenv(resolve(REPO_ROOT, '.env.local')),
  ...parseDotenv(resolve(FRONTEND_DIR, '.env.local')),
}

function required(name: string, ...fallbacks: string[]): string {
  for (const key of [name, ...fallbacks]) {
    const v = process.env[key] ?? fileEnv[key]
    if (v) return v
  }
  throw new Error(
    `E6.2 setup: ${name} is not set. Looked in process.env, frontend/.env.local and .env.local ` +
      `(also tried: ${fallbacks.join(', ') || 'no fallbacks'}). ` +
      `Copy frontend/.env.example to frontend/.env.local and fill it in.`,
  )
}

export const SUPABASE_URL = required('VITE_SUPABASE_URL', 'SUPABASE_URL')
export const SUPABASE_ANON_KEY = required('VITE_SUPABASE_ANON_KEY', 'SUPABASE_ANON_KEY')
export const API_BASE_URL = required('VITE_API_BASE_URL')

/**
 * The localStorage key supabase-js persists the session under.
 *
 * **Derived exactly as the pinned client derives it**, not guessed:
 * `@supabase/supabase-js@2.112.2`, `src/SupabaseClient.ts:329` --
 * `const defaultStorageKey = \`sb-${baseUrl.hostname.split('.')[0]}-auth-token\``
 * -- i.e. the project ref is the first label of the Supabase URL's hostname. `frontend/src/core/
 * auth/supabase.ts` calls `createClient(url, anon)` with no `auth.storageKey` override, so this
 * default is what the app actually reads.
 */
export const SUPABASE_STORAGE_KEY = `sb-${new URL(SUPABASE_URL).hostname.split('.')[0]}-auth-token`

/** Guard: refuse to run the write-bearing race suites against anything but a local API. */
export function assertLocalTarget(): void {
  const host = new URL(API_BASE_URL).hostname
  const isLocal = host === 'localhost' || host === '127.0.0.1' || host === '::1'
  if (!isLocal && process.env.E2E_ALLOW_REMOTE !== 'true') {
    throw new Error(
      `E6.2 refuses to run against a non-local API base (${host}).\n` +
        `These suites WRITE (double-confirm, concurrent takeover, policy publish) and issue #43 ` +
        `forbids driving the production URLs with race writes.\n` +
        `Start the local backend (cd backend && uv run uvicorn app.main:app --port 8000) and ` +
        `point frontend/.env.local's VITE_API_BASE_URL at it, or set E2E_ALLOW_REMOTE=true if you ` +
        `genuinely mean to.`,
    )
  }
}
