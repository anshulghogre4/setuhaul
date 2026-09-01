import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { RoleKey } from './accounts'

const HERE = dirname(fileURLToPath(import.meta.url))

/** Gitignored via `tests/.gitignore` -- these files hold real access and refresh tokens. */
export const AUTH_DIR = resolve(HERE, '../.auth')

/**
 * One file per role. This function is the ONLY place a storageState path is constructed, so
 * "distinct paths per role" is a property of the code rather than of everyone remembering it --
 * which is exactly the failure `TESTING_STRATEGY.md` §4 warns silently invalidates a race suite.
 */
export function storageStatePath(role: RoleKey): string {
  return resolve(AUTH_DIR, `${role}.json`)
}
