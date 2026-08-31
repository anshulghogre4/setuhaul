/**
 * Headless render + measurement pass over every built surface.
 *
 * WHY THIS EXISTS
 * ---------------
 * E5.2, E5.3, E5.4's rewire, E5.5, E5.6, the planner queue UI, the ops composer and the admin
 * policy editor every one of them shipped with "not verified: no browser render -- Playwright
 * absent from frontend/node_modules". They were right to say so rather than imply otherwise.
 * This closes that gap by measuring instead of eyeballing.
 *
 * WHAT IT MEASURES (bars come from the design workspace, not from this file)
 *   - console + page errors, per surface, per theme
 *   - contrast against each element's EFFECTIVE background, including inherited opacity
 *     (color.md: 4.5:1 normal text, 3:1 large text and UI components)
 *   - tap targets against the per-surface floor from spacing-and-layout.md L33:
 *     compact 32 (planner/ops, the deliberate desktop exception) / comfortable 44 /
 *     spacious 56 (gate -- gloved hands, outdoors), plus WCAG 2.2 SC 2.5.8's 24x24 hard floor
 *   - type floor from typography.md L156: 11px everywhere, 14px on driver and gate.
 *     aria-hidden decorative glyphs are a stated exclusion and are skipped.
 *   - ARIA landmarks, duplicate ids, tab<->tabpanel wiring, live regions, unnamed controls
 *
 * THEMES
 * `index.html`'s boot script keys off localStorage `setuhaul.theme` (light | dark | system) and
 * only consults `prefers-color-scheme` for the explicit "system" choice (U69 locks light as the
 * shipped default for every role). There is no `data-theme` attribute -- the opt-in is that
 * localStorage key plus a `.dark` class on <html>. So this drives both media directions AND the
 * explicit opt-in, and asserts the U69 default holds.
 *
 * USAGE
 *   npm run build && npx vite preview --port 4173
 *   node scripts/render-audit.mjs [--base http://localhost:4173] [--out audit.json]
 */
import { chromium } from 'playwright'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'

const argv = process.argv.slice(2)
function arg(name, fallback) {
  const i = argv.indexOf('--' + name)
  return i >= 0 ? argv[i + 1] : fallback
}
const BASE = arg('base', 'http://localhost:4173')
const OUT = arg('out', path.join(import.meta.dirname, '..', 'audit-report.json'))
const ONLY = arg('only', null)

const probeSource = readFileSync(path.join(import.meta.dirname, 'probe.js'), 'utf8')

/**
 * Per-surface floors. Density is NOT guessed -- it mirrors `DENSITY_BY_SURFACE` in
 * `src/core/auth/identity.ts` L115-122, which itself is verbatim from spacing-and-layout.md.
 */
const ROUTES = [
  { path: '/signin',          name: 'signin',          density: 'auth',        tap: 44, type: 11, vw: 1440, vh: 900 },
  { path: '/_states',         name: 'shared-shell',    density: 'mixed',       tap: 32, type: 11, vw: 1600, vh: 1200 },
  { path: '/driver',          name: 'driver',          density: 'comfortable', tap: 44, type: 14, vw: 390,  vh: 844 },
  { path: '/driver/_states',  name: 'driver-gallery',  density: 'comfortable', tap: 44, type: 14, vw: 1440, vh: 1200 },
  { path: '/ops',             name: 'ops',             density: 'compact',     tap: 32, type: 11, vw: 1440, vh: 900 },
  { path: '/ops/_states',     name: 'ops-gallery',     density: 'compact',     tap: 32, type: 11, vw: 1600, vh: 1200 },
  { path: '/planner',         name: 'planner',         density: 'compact',     tap: 32, type: 11, vw: 1440, vh: 900 },
  { path: '/planner/_states', name: 'planner-gallery', density: 'compact',     tap: 32, type: 11, vw: 1600, vh: 1200 },
  { path: '/gate',            name: 'gate',            density: 'spacious',    tap: 56, type: 14, vw: 1280, vh: 800 },
  { path: '/gate/_states',    name: 'gate-gallery',    density: 'spacious',    tap: 56, type: 14, vw: 1440, vh: 1200 },
  { path: '/carrier',         name: 'carrier',         density: 'comfortable', tap: 44, type: 11, vw: 1440, vh: 900 },
  { path: '/carrier/_states', name: 'carrier-gallery', density: 'comfortable', tap: 44, type: 11, vw: 1600, vh: 1200 },
  { path: '/admin',           name: 'admin',           density: 'comfortable', tap: 44, type: 11, vw: 1440, vh: 900 },
  { path: '/admin/_states',   name: 'admin-gallery',   density: 'comfortable', tap: 44, type: 11, vw: 1600, vh: 1200 },
  { path: '/settings',        name: 'settings',        density: 'comfortable', tap: 44, type: 11, vw: 1440, vh: 900 },
]

/** The five theme resolutions worth driving. `expect` asserts U69's locked-light default. */
const THEME_MODES = [
  { id: 'light',            storage: 'light',  media: 'light', expect: 'light', full: true },
  { id: 'dark',             storage: 'dark',   media: 'light', expect: 'dark',  full: true },
  { id: 'default-pref-dark', storage: null,    media: 'dark',  expect: 'light', full: false },
  { id: 'system-pref-dark', storage: 'system', media: 'dark',  expect: 'dark',  full: false },
  { id: 'system-pref-light', storage: 'system', media: 'light', expect: 'light', full: false },
]

const NETWORK_NOISE =
  /(Failed to fetch|net::ERR_|ERR_CONNECTION|NetworkError|Load failed|ERR_NAME_NOT_RESOLVED|fonts\.googleapis|fonts\.gstatic)/i

async function run() {
  const browser = await chromium.launch()
  const report = { base: BASE, startedAt: new Date().toISOString(), surfaces: {} }

  for (const route of ROUTES) {
    if (ONLY && !route.name.includes(ONLY)) continue
    report.surfaces[route.name] = { path: route.path, floors: { tap: route.tap, type: route.type }, themes: {} }

    for (const mode of THEME_MODES) {
      const context = await browser.newContext({
        viewport: { width: route.vw, height: route.vh },
        colorScheme: mode.media,
        reducedMotion: 'reduce',
        deviceScaleFactor: 1,
      })
      // Must run before the inline boot script in index.html reads it.
      await context.addInitScript((choice) => {
        try {
          if (choice === null) localStorage.removeItem('setuhaul.theme')
          else localStorage.setItem('setuhaul.theme', choice)
        } catch {
          /* storage blocked in this context; the boot script falls through to light */
        }
      }, mode.storage)

      const page = await context.newPage()
      const consoleErrors = []
      const pageErrors = []
      const consoleWarnings = []
      page.on('console', (msg) => {
        const t = msg.type()
        const text = msg.text()
        if (t === 'error') consoleErrors.push(text)
        else if (t === 'warning') consoleWarnings.push(text)
      })
      page.on('pageerror', (err) => pageErrors.push(err.message + '\n' + (err.stack || '').split('\n').slice(0, 4).join('\n')))

      let navError = null
      try {
        await page.goto(BASE + route.path, { waitUntil: 'networkidle', timeout: 45000 })
      } catch (e) {
        navError = e.message
        try {
          await page.goto(BASE + route.path, { waitUntil: 'domcontentloaded', timeout: 20000 })
        } catch { /* recorded below */ }
      }
      // Let lazy gallery chunks, Suspense boundaries and fetch-driven states settle.
      await page.waitForTimeout(1800)

      const resolvedTheme = await page.evaluate(() =>
        document.documentElement.classList.contains('dark') ? 'dark' : 'light',
      )

      const entry = {
        resolvedTheme,
        expectedTheme: mode.expect,
        themeResolutionOk: resolvedTheme === mode.expect,
        navError,
        consoleErrors: consoleErrors.filter((e) => !NETWORK_NOISE.test(e)),
        networkErrors: consoleErrors.filter((e) => NETWORK_NOISE.test(e)),
        pageErrors,
        consoleWarnings: consoleWarnings.slice(0, 20),
      }

      if (mode.full) {
        await page.addScriptTag({ content: probeSource })
        entry.measurements = await page.evaluate(
          ({ tapFloor, typeFloor }) => globalThis.__setuhaulProbe({ tapFloor, typeFloor }),
          { tapFloor: route.tap, typeFloor: route.type },
        )
        const shotDir = path.join(import.meta.dirname, '..', 'audit-screenshots')
        mkdirSync(shotDir, { recursive: true })
        await page.screenshot({
          path: path.join(shotDir, `${route.name}-${mode.id}.png`),
          fullPage: false,
        })
      }

      report.surfaces[route.name].themes[mode.id] = entry
      await context.close()
      process.stdout.write(`  ${route.name}/${mode.id} theme=${resolvedTheme}${entry.themeResolutionOk ? '' : ' MISMATCH'} err=${entry.consoleErrors.length}/${entry.pageErrors.length}\n`)
    }
  }

  await browser.close()
  report.finishedAt = new Date().toISOString()
  writeFileSync(OUT, JSON.stringify(report, null, 2))
  console.log('\nWrote ' + OUT)
}

run().catch((e) => {
  console.error(e)
  process.exit(1)
})
