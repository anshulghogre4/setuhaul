/**
 * Verifies the specific structural claims made by M5 surface builders who could not render.
 *
 * Each check below restates the claim it is testing, then measures it. A claim that does not
 * hold is reported as not holding -- that is the point of the exercise, not an accusation.
 *
 * !! READ THIS BEFORE TRUSTING THIS FILE'S OUTPUT !!
 * Four of the verdicts printed here are WRONG, and are kept only as the record of how they were
 * wrong. GATE-2, ADMIN-1, ADMIN-2 and PLAN-1 all report FAILS/PARTIAL because of defects in the
 * CHECKS, not in the product -- a specimen swatch plate counted as a screen, a `useId()` format
 * assumed from memory, a route with no backend data to open a dialog from, and a search for a
 * literal "0:30" when "the 30-second row" is an artboard's name.
 * `verify-claims-2.mjs` re-runs those four correctly; all ten claims hold there. Run BOTH.
 *
 *   npx vite preview --port 4173
 *   node scripts/verify-claims.mjs && node scripts/verify-claims-2.mjs
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE || 'http://localhost:4173'
const results = []
function record(id, claim, held, detail) {
  results.push({ id, claim, held, detail })
  const mark = held === true ? 'HOLDS   ' : held === false ? 'FAILS   ' : 'PARTIAL '
  console.log(`${mark} ${id}  ${claim}`)
  if (detail) console.log('         ' + JSON.stringify(detail))
}

const browser = await chromium.launch()

async function open(route, vw = 1440, vh = 1000, theme = 'light') {
  const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, colorScheme: 'light', reducedMotion: 'reduce' })
  await ctx.addInitScript((t) => { try { localStorage.setItem('setuhaul.theme', t) } catch { /* blocked */ } }, theme)
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 })
  await page.waitForTimeout(1500)
  return { ctx, page, errors }
}

// ---------------------------------------------------------------- GATE

{
  const { ctx, page } = await open('/gate/_states', 1440, 1200)

  // CLAIM: "0 of 76 interactive elements under 56px"
  const gate = await page.evaluate(() => {
    const sel = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=option],[tabindex]:not([tabindex="-1"])'
    const els = Array.from(document.querySelectorAll(sel)).filter((el) => {
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      return cs.display !== 'none' && cs.visibility !== 'hidden' && (r.width || r.height)
    })
    const under = els
      .map((el) => { const r = el.getBoundingClientRect(); return { min: Math.min(r.width, r.height), label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30), w: Math.round(r.width), h: Math.round(r.height) } })
      .filter((x) => x.min + 0.5 < 56)
    return { total: els.length, under }
  })
  record(
    'GATE-1',
    '"0 of 76 interactive elements under 56px"',
    gate.under.length === 0,
    { measuredTotal: gate.total, claimedTotal: 76, under56: gate.under.length, examples: gate.under.slice(0, 5) },
  )

  // CLAIM: "exactly one primary action per screen, zero on screens 12 and 22a"
  // The gate surface uses its own button component; a "primary action" is the filled
  // accent CTA. Detect by computed background matching the primary token, per artboard.
  const perScreen = await page.evaluate(() => {
    const sections = Array.from(document.querySelectorAll('section'))
    return sections.map((s) => {
      const heading = (s.querySelector('h2,h3,[class*=label]') || {}).textContent || ''
      const btns = Array.from(s.querySelectorAll('button,[role=button]')).filter((b) => {
        const cs = getComputedStyle(b)
        const r = b.getBoundingClientRect()
        if (!r.height) return false
        // Filled CTA: opaque non-transparent background that is not the card/surface colour.
        return cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && r.height >= 48
      })
      return { screen: heading.trim().slice(0, 42), filledCtas: btns.length, labels: btns.map((b) => (b.textContent || '').trim().slice(0, 22)) }
    })
  })
  const multi = perScreen.filter((s) => s.filledCtas > 1)
  const zero = perScreen.filter((s) => s.filledCtas === 0)
  record(
    'GATE-2',
    '"exactly one primary action per screen, zero on screens 12 and 22a"',
    multi.length === 0 ? (zero.length >= 1 ? true : 'partial') : false,
    { artboards: perScreen.length, withMoreThanOne: multi, withZero: zero.map((z) => z.screen) },
  )
  await ctx.close()
}

// ---------------------------------------------------------------- CARRIER

{
  const { ctx, page } = await open('/carrier/_states', 1600, 1200)

  // CLAIM: uniform 45px rows
  const rows = await page.evaluate(() =>
    Array.from(document.querySelectorAll('tbody tr'))
      .map((tr) => Math.round(tr.getBoundingClientRect().height * 100) / 100)
      .filter((h) => h > 0),
  )
  const uniq = [...new Set(rows)]
  record('CARR-1', 'carrier rows are a uniform 45px', uniq.length === 1 && Math.abs(uniq[0] - 45) < 0.6, {
    distinctHeights: uniq, rowCount: rows.length,
  })

  // CLAIM: "30 interactive elements, ZERO mutating affordances" (surface is read-only)
  const inter = await page.evaluate(() => {
    const sel = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=option],[tabindex]:not([tabindex="-1"])'
    return Array.from(document.querySelectorAll(sel))
      .filter((el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return cs.display !== 'none' && (r.width || r.height) })
      .map((el) => ({ tag: el.tagName.toLowerCase(), type: el.getAttribute('type'), label: (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || '').trim().slice(0, 34) }))
  })
  const MUTATING = /\b(confirm|reject|cancel|accept|approve|deny|save|submit|delete|remove|edit|update|create|invite|publish|assign|reassign|resolve|acknowledge|block|hold|counter|send|book|request slot)\b/i
  const suspects = inter.filter((e) => MUTATING.test(e.label))
  record('CARR-2', '"30 interactive elements, zero mutating affordances"', suspects.length === 0, {
    measuredInteractive: inter.length, claimed: 30, mutatingSuspects: suspects,
  })

  await ctx.close()
}

{
  // CLAIM: the row-click delegate actually navigates.
  const { ctx, page } = await open('/carrier/_states', 1600, 1200)
  const before = page.url()
  const clicked = await page.evaluate(() => {
    const tr = document.querySelector('tbody tr')
    if (!tr) return false
    const cell = tr.querySelector('td')
    ;(cell || tr).dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }))
    return true
  })
  await page.waitForTimeout(900)
  const after = page.url()
  record('CARR-3', 'row-click delegate actually navigates', clicked && after !== before, {
    clickedARow: clicked, before, after,
  })
  await ctx.close()
}

// ---------------------------------------------------------------- ADMIN

{
  const { ctx, page } = await open('/admin', 1440, 1000)

  // CLAIM: four separate tabpanels with useId-derived ids
  const tabs = await page.evaluate(() => {
    const t = Array.from(document.querySelectorAll('[role=tab]'))
    const p = Array.from(document.querySelectorAll('[role=tabpanel]'))
    return {
      tabCount: t.length,
      panelCount: p.length,
      panelIds: p.map((x) => x.id),
      controls: t.map((x) => x.getAttribute('aria-controls')),
      labelledby: p.map((x) => x.getAttribute('aria-labelledby')),
      tabIds: t.map((x) => x.id),
      // useId() emits ids containing a colon in React 19 (e.g. ":r1:"), never hand-written.
      looksLikeUseId: p.every((x) => /[:«»]/.test(x.id || '')) && t.every((x) => /[:«»]/.test(x.id || '')),
      allDistinct: new Set(p.map((x) => x.id)).size === p.length,
      wiringOk: t.every((x) => { const el = document.getElementById(x.getAttribute('aria-controls') || ''); return el && el.getAttribute('role') === 'tabpanel' }),
    }
  })
  record('ADMIN-1', 'four separate tabpanels with useId-derived ids', tabs.panelCount === 4 && tabs.allDistinct && tabs.looksLikeUseId && tabs.wiringOk, tabs)

  await ctx.close()
}

{
  // CLAIM: the typed-confirmation button is aria-disabled + focusable, NOT html `disabled`.
  const { ctx, page } = await open('/admin', 1440, 1000)
  // Reach the remove-user dialog. The Users tab is default; find a remove affordance.
  const opened = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /remove|delete/i.test((b.getAttribute('aria-label') || b.textContent || '')),
    )
    if (!btn) return false
    btn.click()
    return true
  })
  await page.waitForTimeout(700)
  const dlg = await page.evaluate(() => {
    const scope = document.querySelector('[role=dialog],[role=alertdialog]') || document
    const btn = Array.from(scope.querySelectorAll('button')).find((b) =>
      /remove|confirm|delete/i.test(b.textContent || ''),
    )
    if (!btn) return { found: false, dialogPresent: !!document.querySelector('[role=dialog],[role=alertdialog]') }
    return {
      found: true,
      dialogPresent: true,
      hasHtmlDisabled: btn.hasAttribute('disabled'),
      ariaDisabled: btn.getAttribute('aria-disabled'),
      tabIndex: btn.tabIndex,
      describedBy: btn.getAttribute('aria-describedby'),
      title: btn.getAttribute('title'),
      label: (btn.textContent || '').trim().slice(0, 40),
    }
  })
  record(
    'ADMIN-2',
    'typed-confirmation button is aria-disabled + focusable, not html disabled',
    dlg.found ? dlg.hasHtmlDisabled === false && dlg.ariaDisabled === 'true' && dlg.tabIndex >= 0 : 'partial',
    { openedRemoveControl: opened, ...dlg },
  )
  await ctx.close()
}

// ---------------------------------------------------------------- PLANNER

{
  const { ctx, page } = await open('/planner/_states', 1600, 1400)
  const planner = await page.evaluate(() => {
    const text = document.body.innerText
    const mono = Array.from(document.querySelectorAll('[class*=font-mono],[class*=tabular]'))
      .map((e) => (e.textContent || '').trim())
      .filter((t) => /^\d+:\d{2}$/.test(t))
    return {
      countdownValues: [...new Set(mono)],
      hasThirtySecondRow: mono.some((t) => t === '0:30') || /\b0:30\b/.test(text),
      hasExpiredRow: mono.some((t) => t === '0:00'),
      refusalMentions: (text.match(/refus|cannot|unable|not available|no longer|declin/gi) || []).length,
      queueRowCount: document.querySelectorAll('[role=option]').length,
      notYetAvailableBlocks: (text.match(/not yet available|Not yet available/g) || []).length,
    }
  })
  record('PLAN-1', 'the 30-second queue row renders', planner.hasThirtySecondRow, planner)

  // CLAIM: refusal states render in place (inside the row/dialog, not as a toast).
  const refusal = await page.evaluate(() => {
    const toasts = document.querySelectorAll('[data-sonner-toast],[data-sonner-toaster] li').length
    const inPlace = Array.from(document.querySelectorAll('[role=alert],[role=status]')).filter((e) =>
      /refus|cannot|unable|no longer|already|conflict|denied/i.test(e.textContent || ''),
    ).length
    return { toastNodes: toasts, inPlaceRefusalRegions: inPlace }
  })
  record('PLAN-2', 'refusal states render in place, not as a toast', refusal.inPlaceRefusalRegions > 0 && refusal.toastNodes === 0, refusal)
  await ctx.close()
}

// ---------------------------------------------------------------- OPS

{
  const { ctx, page } = await open('/ops/_states', 1600, 1400)
  const ops = await page.evaluate(() => {
    const toasts = document.querySelectorAll('[data-sonner-toast]').length
    const markers = Array.from(document.querySelectorAll('*')).filter(
      (e) => e.children.length === 0 && /not delivered|undelivered|didn.t send|not sent|failed to send/i.test(e.textContent || ''),
    )
    return {
      sonnerToastNodes: toasts,
      persistentMarkers: markers.length,
      markerSamples: markers.slice(0, 4).map((m) => ({ text: (m.textContent || '').trim().slice(0, 70), role: m.closest('[role]') ? m.closest('[role]').getAttribute('role') : null, inTranscript: !!m.closest('ol,ul,[role=log],[role=list]') })),
    }
  })
  record(
    'OPS-1',
    "composer's `delivered: false` renders as a persistent per-message marker, not a toast",
    ops.persistentMarkers > 0 && ops.sonnerToastNodes === 0,
    ops,
  )
  await ctx.close()
}

await browser.close()
console.log('\n' + JSON.stringify({ results }, null, 2))
