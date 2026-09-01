import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

import { REPO_ROOT } from './env'
import type { Bucket } from './accounts'

/**
 * Resolves the three shared POC bucket passwords **without ever committing one**.
 *
 * Precedence, deliberately environment-first so CI can supply secrets without a file:
 *   1. `SETUHAUL_E2E_{DRIVER,OPERATIONS,ADMIN}_PASSWORD` from the process environment.
 *   2. The gitignored `POC_TEAM_ACCOUNTS.local.md` at the repo root -- its "Shared passwords
 *      (3 buckets)" table, which is a stable three-row markdown table keyed by bucket name.
 *
 * The repo-root `.env`/`.env.local` carry `SETUHAUL_POC_*_PASSWORD` keys but they are **empty
 * placeholders** -- verified 2026-09-01, all six are zero-length, and `.env` says so in a comment
 * ("Do not store POC passwords in this file"). So they are not consulted; reading them would just
 * produce a confusing empty-password 400 from the token endpoint.
 *
 * Nothing in this module logs a value. The only thing it will ever print is a bucket NAME in an
 * error message.
 */

const ROSTER = resolve(REPO_ROOT, 'POC_TEAM_ACCOUNTS.local.md')

let cached: Partial<Record<Bucket, string>> | null = null

function fromRoster(): Partial<Record<Bucket, string>> {
  if (!existsSync(ROSTER)) return {}
  const out: Partial<Record<Bucket, string>> = {}
  for (const line of readFileSync(ROSTER, 'utf8').split(/\r?\n/)) {
    // | Driver | <password> | All DRIVER users |
    const m = line.match(/^\|\s*(Driver|Operations|Admin)\s*\|\s*(\S+)\s*\|/)
    if (m) out[m[1] as Bucket] = m[2]
  }
  return out
}

const ENV_KEY: Record<Bucket, string> = {
  Driver: 'SETUHAUL_E2E_DRIVER_PASSWORD',
  Operations: 'SETUHAUL_E2E_OPERATIONS_PASSWORD',
  Admin: 'SETUHAUL_E2E_ADMIN_PASSWORD',
}

export function passwordFor(bucket: Bucket): string {
  cached ??= fromRoster()
  const value = process.env[ENV_KEY[bucket]] ?? cached[bucket]
  if (!value) {
    throw new Error(
      `E6.2 setup: no password available for the "${bucket}" bucket.\n` +
        `Set ${ENV_KEY[bucket]} in the environment, or make sure the gitignored ` +
        `POC_TEAM_ACCOUNTS.local.md exists at the repo root with its "Shared passwords (3 buckets)" ` +
        `table intact. (Secrets are never read from a committed file and never printed.)`,
    )
  }
  return value
}
