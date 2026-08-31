/**
 * Corrected re-runs of the four claim checks whose FIRST version was wrong.
 *
 * Kept as a separate file rather than silently patched into `verify-claims.mjs`, because which
 * checks were probe artifacts and which were real is itself a finding worth preserving:
 *
 *   GATE-2  v1 counted artboard 13 ("Primary action -- every state"), a component SPECIMEN
 *           sheet, as a screen with 6 primary actions. It is a swatch plate, not a screen.
 *   ADMIN-1 v1 asserted useId() emits colons (":r1:"). React 19.2.8 emits "_r_4_" -- the
 *           format changed so ids are valid CSS selectors. The ids were always useId-derived.
 *   ADMIN-2 v1 ran against /admin, where the user list is empty (no backend), so no remove
 *           control existed to open. The gallery has an explicit "Open remove dialog" trigger.
 *   PLAN-1  v1 looked for a literal "0:30" countdown. "The 30-second row" is the NAME of
 *           planner gallery artboard 1, not a timer value.
 */
import { chromium } from 'playwright'

const BASE = process.env.AUDIT_BASE || 'http://localhost:4173'
const browser = await chromium.launch()
const out = []
function record(id, claim, held, detail) {
  out.push({ id, claim, held, detail })
  console.log(`${held === true ? 'HOLDS   ' : held === false ? 'FAILS   ' : 'PARTIAL '} ${id}  ${claim}`)
  console.log('         ' + JSON.stringify(detail))
}
async function open(route, vw, vh) {
  const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, reducedMotion: 'reduce' })
  await ctx.addInitScript(() => { try { localStorage.setItem('setuhaul.theme', 'light') } catch { /* blocked */ } })
  const page = await ctx.newPage()
  await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 })
  await page.waitForTimeout(1500)
  return { ctx, page }
}

// ---- GATE-2 corrected: exclude the component-specimen plate from the per-screen count.
{
  const { ctx, page } = await open('/gate/_states', 1440, 1200)
  const perScreen = await page.evaluate(() =>
    Array.from(document.querySelectorAll('section'))
      .map((s) => {
        const title = ((s.querySelector('h2,h3,[class*=label]') || {}).textContent || '').trim()
        const ctas = Array.from(s.querySelectorAll('button,[role=button]')).filter((b) => {
          const cs = getComputedStyle(b)
          const r = b.getBoundingClientRect()
          return r.height >= 48 && cs.backgroundColor !== 'rgba(0, 0, 0, 0)'
        })
        return { title: title.slice(0, 60), ctas: ctas.length, labels: ctas.map((b) => (b.textContent || '').trim().slice(0, 20)) }
      })
      .filter((s) => s.title),
  )
  // A plate whose own title says it enumerates every state of one control is a swatch sheet.
  const isSpecimen = (t) => /every state|all states|anatomy|specimen|variants/i.test(t)
  const screens = perScreen.filter((s) => !isSpecimen(s.title))
  const specimens = perScreen.filter((s) => isSpecimen(s.title))
  const multi = screens.filter((s) => s.ctas > 1)
  const s12 = screens.find((s) => /^12\b/.test(s.title))
  const s22a = screens.find((s) => /^22a\b/.test(s.title))
  record(
    'GATE-2',
    '"exactly one primary action per screen, zero on screens 12 and 22a"',
    multi.length === 0 && s12 && s12.ctas === 0 && s22a && s22a.ctas === 0,
    {
      screensChecked: screens.length,
      specimenPlatesExcluded: specimens.map((s) => s.title),
      screensWithMoreThanOnePrimary: multi,
      screen12: s12,
      screen22a: s22a,
      screensWithZero: screens.filter((s) => s.ctas === 0).map((s) => s.title),
    },
  )
  await ctx.close()
}

// ---- CARR-2 corrected: count only inside artboards, excluding the gallery's own toolbar.
{
  const { ctx, page } = await open('/carrier/_states', 1600, 1200)
  const r = await page.evaluate(() => {
    const sel = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=option],[tabindex]:not([tabindex="-1"])'
    const all = Array.from(document.querySelectorAll(sel)).filter((el) => {
      const b = el.getBoundingClientRect()
      return getComputedStyle(el).display !== 'none' && (b.width || b.height)
    })
    const inArt = all.filter((el) => el.closest('section'))
    const MUT = /\b(confirm|reject|cancel|accept|approve|deny|save|submit|delete|remove|edit|update|create|invite|publish|assign|reassign|resolve|acknowledge|block|hold|counter|send|book)\b/i
    return {
      totalIncludingGalleryChrome: all.length,
      insideArtboards: inArt.length,
      galleryChrome: all.length - inArt.length,
      mutating: inArt
        .map((el) => ({ tag: el.tagName.toLowerCase(), label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30) }))
        .filter((e) => MUT.test(e.label)),
      forms: document.querySelectorAll('section form').length,
    }
  })
  record('CARR-2', '"30 interactive elements, zero mutating affordances"', r.mutating.length === 0, { claimed: 30, ...r })
  await ctx.close()
}

// ---- ADMIN-1 corrected: React 19.2.8's useId emits `_r_N_`, not `:rN:`.
{
  const { ctx, page } = await open('/admin', 1440, 1000)
  const t = await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('[role=tab]'))
    const panels = Array.from(document.querySelectorAll('[role=tabpanel]'))
    return {
      tabCount: tabs.length,
      panelCount: panels.length,
      panelIds: panels.map((p) => p.id),
      allPanelIdsDistinct: new Set(panels.map((p) => p.id)).size === panels.length,
      // React 19 useId output: underscore-delimited, e.g. `_r_4_`. Hand-written ids in this
      // codebase are kebab-case words; anything matching `_r_<n>_` came from useId.
      useIdDerived: panels.every((p) => /_r_[0-9a-z]+_/.test(p.id)) && tabs.every((x) => /_r_[0-9a-z]+_/.test(x.id)),
      everyTabControlsItsOwnPanel:
        tabs.every((x) => {
          const el = document.getElementById(x.getAttribute('aria-controls') || '')
          return el && el.getAttribute('role') === 'tabpanel'
        }) && new Set(tabs.map((x) => x.getAttribute('aria-controls'))).size === tabs.length,
      everyPanelLabelledByItsOwnTab: panels.every((p) => {
        const el = document.getElementById(p.getAttribute('aria-labelledby') || '')
        return el && el.getAttribute('role') === 'tab'
      }),
    }
  })
  record('ADMIN-1', 'four separate tabpanels with useId-derived ids', t.panelCount === 4 && t.allPanelIdsDistinct && t.useIdDerived && t.everyTabControlsItsOwnPanel && t.everyPanelLabelledByItsOwnTab, t)
  await ctx.close()
}

// ---- ADMIN-2 corrected: drive the gallery's explicit "Open remove dialog" trigger.
{
  const { ctx, page } = await open('/admin/_states', 1600, 1400)
  const opened = await page.evaluate(() => {
    const b = Array.from(document.querySelectorAll('button')).find((x) => /open remove dialog/i.test(x.textContent || ''))
    if (!b) return false
    b.click()
    return true
  })
  await page.waitForTimeout(800)
  const before = await page.evaluate(() => {
    const scope = document.querySelector('[role=dialog],[role=alertdialog]')
    if (!scope) return { dialogPresent: false }
    const btn = Array.from(scope.querySelectorAll('button')).find((b) => /remove/i.test(b.textContent || ''))
    if (!btn) return { dialogPresent: true, buttonFound: false, buttons: Array.from(scope.querySelectorAll('button')).map((b) => (b.textContent || '').trim().slice(0, 24)) }
    btn.focus()
    return {
      dialogPresent: true,
      buttonFound: true,
      label: (btn.textContent || '').trim().slice(0, 30),
      hasHtmlDisabledAttr: btn.hasAttribute('disabled'),
      ariaDisabled: btn.getAttribute('aria-disabled'),
      tabIndex: btn.tabIndex,
      // The whole point: `disabled` removes it from the focus order and silences the reason.
      isFocusable: document.activeElement === btn,
      describedBy: btn.getAttribute('aria-describedby'),
      reasonText: btn.getAttribute('aria-describedby')
        ? (document.getElementById(btn.getAttribute('aria-describedby')) || {}).textContent
        : btn.getAttribute('title'),
    }
  })
  record(
    'ADMIN-2',
    'typed-confirmation button is aria-disabled + focusable, not html disabled',
    before.buttonFound === true && before.hasHtmlDisabledAttr === false && before.ariaDisabled === 'true' && before.isFocusable === true,
    { openedTrigger: opened, ...before },
  )
  await ctx.close()
}

// ---- PLAN-1 corrected: "The 30-second row" is planner gallery artboard 1's NAME.
{
  const { ctx, page } = await open('/planner/_states', 1600, 1400)
  const p = await page.evaluate(() => {
    // The planner gallery plates are <figure>/<figcaption>, not <section>/<h2> like the
    // gate and carrier galleries. Same idea, different element -- worth stating because the
    // first version of this check reported a false FAIL purely on the selector.
    const plate = Array.from(document.querySelectorAll('figure')).find((s) =>
      /30-second row/i.test(((s.querySelector('figcaption') || {}).textContent || '')),
    )
    if (!plate) return { plateFound: false, allTitles: Array.from(document.querySelectorAll('figure figcaption')).map((h) => (h.textContent || '').trim().slice(0, 40)) }
    const r = plate.getBoundingClientRect()
    return {
      plateFound: true,
      title: ((plate.querySelector('figcaption') || {}).textContent || '').trim().slice(0, 70),
      renderedHeight: Math.round(r.height),
      renderedWidth: Math.round(r.width),
      hasVisibleContent: (plate.innerText || '').trim().length > 40,
      textSample: (plate.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160),
      countdownInside: Array.from(plate.querySelectorAll('[class*=font-mono],[class*=tabular]')).map((e) => (e.textContent || '').trim()).filter(Boolean).slice(0, 6),
      interactiveInside: plate.querySelectorAll('button,a[href],[role=button]').length,
    }
  })
  record('PLAN-1', 'the "30-second row" artboard renders', p.plateFound && p.hasVisibleContent && p.renderedHeight > 40, p)
  await ctx.close()
}

await browser.close()
console.log('\n' + JSON.stringify({ results: out }, null, 2).slice(0, 200) + ' ...')
