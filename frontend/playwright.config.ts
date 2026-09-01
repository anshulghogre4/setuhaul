import { defineConfig, devices } from 'playwright/test'

/**
 * E6.2 (issue #43) -- the seven UI-race suites from `TESTING_STRATEGY.md` §4.
 *
 * ## Why `playwright/test` and not `@playwright/test`
 *
 * `package.json` pins `playwright@1.62.1` as a devDependency and `@playwright/test` is **not**
 * installed. In 1.62.1 the `playwright` package itself ships the runner: its `exports` map has a
 * `"./test"` entry and `node_modules/playwright/test.js` merges `./lib/index` (the runner) with
 * `./index` (the automation library) into one module. Verified by running
 * `node node_modules/playwright/cli.js test --help`, which resolves. So this suite adds **no new
 * dependency** -- deliberately, because adding one would be a bigger change than issue #43's
 * `risk:low` label describes.
 *
 * ## The target is the LOCAL stack, never production
 *
 * These suites WRITE (double-confirm, concurrent takeover, policy publish). `baseURL` therefore
 * defaults to the local vite dev server, which reads `frontend/.env.local` -- where
 * `VITE_API_BASE_URL` is `http://localhost:8000`, the local uvicorn. Driving the CloudFront/Vercel
 * production URLs with race writes is explicitly out of bounds (issue #43's brief), so nothing here
 * reads `.env.production.local`.
 *
 * The backend is NOT started by this config. It needs the shared dev database and its own
 * environment, so starting it as a Playwright `webServer` would hide failures behind a timeout.
 * `tests/auth.setup.ts` probes `/health/live` and fails with a named, actionable message instead.
 *
 * ## storageState
 *
 * Every role gets its own file under `tests/.auth/` (gitignored). There is no shared default
 * `storageState` in `use` below, and that omission is deliberate -- see
 * `tests/storage-state-isolation.spec.ts` for the pitfall it exists to avoid.
 */

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './tests',
  // Kept inside `tests/` so the one nested `tests/.gitignore` covers every generated artifact --
  // traces and failure screenshots as well as the token-bearing storageState files. Playwright's
  // default would drop `test-results/` at the frontend root, outside that ignore.
  outputDir: './tests/.artifacts',
  // A race suite that runs its own two contexts in parallel with ANOTHER race suite's writes is
  // testing interference, not the race. Serial files, parallel contexts inside a file.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [['list']],
  // Races resolve in milliseconds; a long timeout only makes a hung precondition look like a slow
  // test. 60s covers a cold vite transform of the surface under test.
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Races are asserted on what the losing user is TOLD, so a failure screenshot is the evidence.
    video: 'off',
  },

  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'races',
      dependencies: ['setup'],
      testIgnore: /auth\.setup\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    // `npm run dev` (vite) -- reads `.env.local`, so VITE_API_BASE_URL is localhost:8000.
    command: 'npm run dev -- --port 5173 --strictPort',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
})
