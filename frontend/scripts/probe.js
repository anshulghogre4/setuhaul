/**
 * In-page measurement probe, injected by `render-audit.mjs` into a real Chromium page.
 *
 * This file is deliberately a plain browser script (no imports, no build step): it is
 * `page.evaluate`d as a string, so it must not reference anything outside the page.
 *
 * Why it exists: every M5 surface build (E5.2-E5.6) reported "not verified: no browser render"
 * because Playwright was absent from `frontend/node_modules`. Eyeballing a mockup cannot answer
 * "is this text 4.5:1 against its *effective* background, including inherited opacity" or "is
 * this gate control really 56px". Those are measurements, so this measures them.
 *
 * The bars it checks come from the design workspace, not from this file's own opinion:
 *   - contrast          docs/.../UI-UX/00-foundations/color.md  (4.5:1 text, 3:1 large/UI)
 *   - tap targets       spacing-and-layout.md L33 (compact 32 / comfortable 44 / spacious 56)
 *                       and WCAG 2.2 SC 2.5.8's 24x24 absolute floor (L41-46)
 *   - type floor        typography.md L156 (never below 11px; never below 14px on driver/gate)
 */
globalThis.__setuhaulProbe = function probe(options) {
  const opts = options || {}
  const tapFloor = opts.tapFloor || 44
  const typeFloor = opts.typeFloor || 11

  // ---------------------------------------------------------------- colour utilities

  /** Parse any computed colour string Chromium can emit into [r,g,b,a]. */
  function parseColor(str) {
    if (!str) return null
    if (str === 'transparent') return [0, 0, 0, 0]
    const m = str.match(/^rgba?\(([^)]+)\)$/)
    if (m) {
      const parts = m[1].split(/[\s,/]+/).filter(Boolean).map(Number)
      if (parts.length >= 3) return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1]
    }
    // color(srgb r g b / a) — Chromium emits this for oklch()-authored tokens.
    const c = str.match(/^color\(srgb\s+([^)]+)\)$/)
    if (c) {
      const parts = c[1].split(/[\s/]+/).filter(Boolean).map(Number)
      if (parts.length >= 3) {
        return [parts[0] * 255, parts[1] * 255, parts[2] * 255, parts.length > 3 ? parts[3] : 1]
      }
    }
    return null
  }

  /** Composite `fg` (with alpha) over opaque `bg`. */
  function over(fg, bg) {
    const a = fg[3]
    return [
      fg[0] * a + bg[0] * (1 - a),
      fg[1] * a + bg[1] * (1 - a),
      fg[2] * a + bg[2] * (1 - a),
      1,
    ]
  }

  function relLuminance(rgb) {
    const ch = rgb.slice(0, 3).map((v) => {
      const s = v / 255
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
    })
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
  }

  function contrast(a, b) {
    const la = relLuminance(a)
    const lb = relLuminance(b)
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
  }

  /**
   * Effective background behind `el`, honouring inherited `opacity`.
   *
   * The naive version of this check walks up until it finds a non-transparent
   * background-color and stops. That is wrong whenever an ancestor carries `opacity < 1`,
   * because opacity applies to the element as a *group*: the ancestor's own background AND
   * every descendant's paint are blended with whatever sits behind the ancestor. A chip that
   * measures 4.6:1 in isolation can render at 3.1:1 inside an `opacity-70` wrapper.
   *
   * So: build the chain root->element, give each node a cumulative opacity (its own times all
   * ancestors'), then composite every layer's background onto the canvas in paint order.
   * Returns the opaque colour actually behind the element's text, plus the cumulative opacity
   * the text itself is drawn with.
   */
  function effectiveBackground(el) {
    const chain = []
    let node = el
    while (node && node.nodeType === 1) {
      chain.push(node)
      node = node.parentElement
    }
    chain.reverse() // root -> element

    let cumulative = 1
    const layers = []
    let unmeasurable = null
    for (const n of chain) {
      const cs = getComputedStyle(n)
      const o = parseFloat(cs.opacity)
      cumulative *= Number.isNaN(o) ? 1 : o
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        // A gradient or image behind text cannot be reduced to one colour honestly.
        unmeasurable = cs.backgroundImage.slice(0, 60)
      }
      const bg = parseColor(cs.backgroundColor)
      if (bg && bg[3] > 0) layers.push([bg, cumulative])
    }

    // Chromium's default canvas is white; the app sets a background on html/body anyway.
    let canvas = [255, 255, 255, 1]
    for (const [color, op] of layers) {
      canvas = over([color[0], color[1], color[2], color[3] * op], canvas)
    }
    return { bg: canvas, cumulativeOpacity: cumulative, unmeasurable }
  }

  // ---------------------------------------------------------------- traversal helpers

  function isHiddenFromAT(el) {
    let n = el
    while (n && n.nodeType === 1) {
      if (n.getAttribute('aria-hidden') === 'true') return true
      if (n.hasAttribute('inert')) return true
      n = n.parentElement
    }
    return false
  }

  function isRendered(el) {
    const cs = getComputedStyle(el)
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false
    if (parseFloat(cs.opacity) === 0) return false
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) return false
    return true
  }

  /** Text owned directly by `el` (not by its element children). */
  function ownText(el) {
    let t = ''
    for (const child of el.childNodes) {
      if (child.nodeType === 3) t += child.nodeValue
    }
    return t.trim()
  }

  function pathOf(el) {
    const parts = []
    let n = el
    let depth = 0
    while (n && n.nodeType === 1 && depth < 5) {
      let s = n.tagName.toLowerCase()
      if (n.id) s += '#' + n.id
      else if (n.className && typeof n.className === 'string') {
        const cls = n.className.trim().split(/\s+/).slice(0, 3).join('.')
        if (cls) s += '.' + cls
      }
      parts.unshift(s)
      n = n.parentElement
      depth++
    }
    return parts.join(' > ')
  }

  const all = Array.from(document.querySelectorAll('*'))

  // ---------------------------------------------------------------- 1. contrast

  const contrastFindings = []
  const unmeasurableBg = []
  for (const el of all) {
    const text = ownText(el)
    if (!text) continue
    if (isHiddenFromAT(el)) continue
    if (!isRendered(el)) continue
    const tag = el.tagName.toLowerCase()
    if (tag === 'script' || tag === 'style' || tag === 'noscript' || tag === 'title') continue

    const cs = getComputedStyle(el)
    const fg = parseColor(cs.color)
    if (!fg) continue

    const { bg, cumulativeOpacity, unmeasurable } = effectiveBackground(el)
    if (unmeasurable) {
      unmeasurableBg.push({ path: pathOf(el), text: text.slice(0, 40), background: unmeasurable })
      continue
    }

    const fgEff = over([fg[0], fg[1], fg[2], fg[3] * cumulativeOpacity], bg)
    const ratio = contrast(fgEff, bg)

    const size = parseFloat(cs.fontSize)
    const weight = parseInt(cs.fontWeight, 10) || 400
    // WCAG "large text": >= 24px, or >= 18.66px when bold.
    const isLarge = size >= 24 || (size >= 18.66 && weight >= 700)
    const required = isLarge ? 3 : 4.5

    if (ratio + 0.005 < required) {
      contrastFindings.push({
        path: pathOf(el),
        text: text.slice(0, 60),
        ratio: Math.round(ratio * 100) / 100,
        required,
        fontSize: size,
        fontWeight: weight,
        color: cs.color,
        effectiveBg: 'rgb(' + bg.slice(0, 3).map(Math.round).join(', ') + ')',
        cumulativeOpacity: Math.round(cumulativeOpacity * 1000) / 1000,
        inArtboard: !!el.closest('section'),
        disabled: !!(el.closest('[disabled],[aria-disabled="true"],[data-disabled]')),
      })
    }
  }

  // ---------------------------------------------------------------- 2. tap targets

  const INTERACTIVE = [
    'button',
    'a[href]',
    'input:not([type="hidden"])',
    'select',
    'textarea',
    'summary',
    '[role="button"]',
    '[role="tab"]',
    '[role="option"]',
    '[role="menuitem"]',
    '[role="menuitemcheckbox"]',
    '[role="menuitemradio"]',
    '[role="switch"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="link"]',
    '[role="combobox"]',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',')

  const interactives = Array.from(document.querySelectorAll(INTERACTIVE)).filter(
    (el) => isRendered(el) && !isHiddenFromAT(el),
  )

  /**
   * The *effective* target, not the control's own box.
   *
   * Measuring the raw rect over-reports: a 16x16 radio inside a `<label>` is really a
   * label-sized target, because clicking the label activates the input. Same for a control
   * nested in a `role="option"` row that carries the click. Reporting those as 16px defects
   * would inflate the count with things that are not actually hard to hit, so this walks up
   * for a genuinely activating ancestor and takes the larger box.
   *
   * It does NOT credit an arbitrary `<div onClick>` ancestor -- React attaches those via
   * delegation, so there is no DOM-visible signal, and guessing would under-report.
   */
  const ACTIVATING_ANCESTOR = 'label,[role="option"],[role="row"],[role="menuitem"],[role="tab"],a[href],button'
  function effectiveTarget(el) {
    let best = el.getBoundingClientRect()
    let bestVia = 'self'
    // A label only activates a form control it wraps (or points at via `for`).
    const isFormControl = /^(input|select|textarea)$/.test(el.tagName.toLowerCase())
    let n = el.parentElement
    let depth = 0
    while (n && n.nodeType === 1 && depth < 4) {
      const tag = n.tagName.toLowerCase()
      const matches = n.matches && n.matches(ACTIVATING_ANCESTOR)
      const labelActivates = tag === 'label' && isFormControl
      if (matches && (labelActivates || tag !== 'label')) {
        const r = n.getBoundingClientRect()
        if (Math.min(r.width, r.height) > Math.min(best.width, best.height)) {
          best = r
          bestVia = tag + (n.getAttribute('role') ? '[role=' + n.getAttribute('role') + ']' : '')
        }
      }
      n = n.parentElement
      depth++
    }
    return { rect: best, via: bestVia }
  }

  /** Gallery artboards live inside <section> plates; the verification page's own toolbar
   *  does not. Keeps shipped UI separable from the harness chrome around it. */
  function insideArtboard(el) {
    return !!el.closest('section')
  }

  const tapFindings = []
  const wcagFloorFindings = []
  for (const el of interactives) {
    const { rect, via } = effectiveTarget(el)
    const w = Math.round(rect.width * 100) / 100
    const h = Math.round(rect.height * 100) / 100
    const min = Math.min(w, h)
    const own = el.getBoundingClientRect()
    const entry = {
      path: pathOf(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || null,
      label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40),
      width: w,
      height: h,
      min,
      ownWidth: Math.round(own.width * 100) / 100,
      ownHeight: Math.round(own.height * 100) / 100,
      via,
      inArtboard: insideArtboard(el),
      // Kept so the spacing-exception pass below can locate this exact element's geometry.
      // Matching rects back by width/height is not safe -- 27 identical 36x20 switches would
      // all resolve to whichever one happened to be first in the list.
      _cx: rect.left + rect.width / 2,
      _cy: rect.top + rect.height / 2,
    }
    if (min + 0.5 < tapFloor) tapFindings.push(entry)
    if (min + 0.5 < 24) wcagFloorFindings.push(entry)
  }

  /**
   * WCAG 2.2 SC 2.5.8's **Spacing exception**, measured rather than assumed.
   *
   * Verbatim: "Undersized targets ... are positioned so that if a 24 CSS pixel diameter circle
   * is centered on the bounding box of each, the circles do not intersect another target."
   *
   * Without this, a 20px switch on its own row gets reported as a legal-floor breach when it
   * is not one. The product's own 44/56px bars still apply -- they are stricter than WCAG and
   * carry no spacing exception -- so this only reclassifies the *legal* floor, never the
   * product floor.
   */
  const allCentres = interactives.map((el) => {
    const r = effectiveTarget(el).rect
    return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 }
  })
  for (const f of wcagFloorFindings) {
    f.spacingExceptionMet = true
    f.nearestTargetDistance = null
    let nearest = Infinity
    for (const o of allCentres) {
      const d = Math.hypot(f._cx - o.cx, f._cy - o.cy)
      if (d < 0.01) continue // itself
      if (d < nearest) nearest = d
    }
    f.nearestTargetDistance = Number.isFinite(nearest) ? Math.round(nearest * 10) / 10 : null
    // Two 24px-diameter (12px-radius) circles intersect when their centres are < 24px apart.
    if (Number.isFinite(nearest) && nearest < 24) f.spacingExceptionMet = false
  }
  for (const f of tapFindings) { delete f._cx; delete f._cy }
  for (const f of wcagFloorFindings) { delete f._cx; delete f._cy }

  // ---------------------------------------------------------------- 3. type floor

  const typeFindings = []
  for (const el of all) {
    const text = ownText(el)
    if (!text) continue
    if (isHiddenFromAT(el)) continue // decorative glyphs are a stated exclusion
    if (!isRendered(el)) continue
    const size = parseFloat(getComputedStyle(el).fontSize)
    if (size + 0.01 < typeFloor) {
      typeFindings.push({ path: pathOf(el), text: text.slice(0, 40), fontSize: size })
    }
  }

  // ---------------------------------------------------------------- 4. ARIA

  const ids = {}
  for (const el of document.querySelectorAll('[id]')) {
    ids[el.id] = (ids[el.id] || 0) + 1
  }
  const duplicateIds = Object.keys(ids).filter((k) => ids[k] > 1)

  const tabs = Array.from(document.querySelectorAll('[role="tab"]')).filter(isRendered)
  const tabpanels = Array.from(document.querySelectorAll('[role="tabpanel"]'))
  const tabWiring = tabs.map((t) => {
    const controls = t.getAttribute('aria-controls')
    const target = controls ? document.getElementById(controls) : null
    return {
      id: t.id || null,
      label: (t.textContent || '').trim().slice(0, 30),
      ariaControls: controls,
      controlsExists: !!target,
      controlsIsTabpanel: !!target && target.getAttribute('role') === 'tabpanel',
      ariaSelected: t.getAttribute('aria-selected'),
      tabindex: t.getAttribute('tabindex'),
    }
  })
  const panelWiring = tabpanels.map((p) => {
    const by = p.getAttribute('aria-labelledby')
    const target = by ? document.getElementById(by) : null
    return {
      id: p.id || null,
      ariaLabelledby: by,
      labelledbyExists: !!target,
      labelledbyIsTab: !!target && target.getAttribute('role') === 'tab',
      hidden: p.hasAttribute('hidden') || getComputedStyle(p).display === 'none',
    }
  })

  const landmarks = {
    main: document.querySelectorAll('main, [role="main"]').length,
    nav: document.querySelectorAll('nav, [role="navigation"]').length,
    banner: document.querySelectorAll('header, [role="banner"]').length,
    contentinfo: document.querySelectorAll('footer, [role="contentinfo"]').length,
    region: document.querySelectorAll('[role="region"]').length,
    search: document.querySelectorAll('[role="search"]').length,
  }

  const liveRegions = Array.from(
    document.querySelectorAll('[aria-live], [role="status"], [role="alert"], [role="log"]'),
  ).map((el) => ({
    path: pathOf(el),
    ariaLive: el.getAttribute('aria-live'),
    role: el.getAttribute('role'),
    atomic: el.getAttribute('aria-atomic'),
  }))

  // Icon-only controls with no accessible name at all.
  /**
   * Accessible name, resolved in roughly accname order.
   *
   * The naive version (aria-label || textContent) reports every properly-labelled `<input>` as
   * unnamed, because an input has no text content -- its name comes from a `<label for>` or a
   * wrapping `<label>`. That produced four false positives on the first run, so it resolves
   * both label forms here rather than flagging correct markup.
   */
  function accessibleName(el) {
    const labelledby = el.getAttribute('aria-labelledby')
    if (labelledby) {
      const t = labelledby
        .split(/\s+/)
        .map((id) => (document.getElementById(id) || {}).textContent || '')
        .join(' ')
        .trim()
      if (t) return t
    }
    const aria = (el.getAttribute('aria-label') || '').trim()
    if (aria) return aria
    if (el.id) {
      const forLabel = document.querySelector('label[for="' + CSS.escape(el.id) + '"]')
      if (forLabel && (forLabel.textContent || '').trim()) return forLabel.textContent.trim()
    }
    const wrapping = el.closest('label')
    if (wrapping && (wrapping.textContent || '').trim()) return wrapping.textContent.trim()
    const title = (el.getAttribute('title') || '').trim()
    if (title) return title
    const ph = (el.getAttribute('placeholder') || '').trim()
    if (ph) return ph
    const alt = Array.from(el.querySelectorAll('img[alt]'))
      .map((i) => i.getAttribute('alt'))
      .join(' ')
      .trim()
    if (alt) return alt
    return (el.textContent || '').trim()
  }

  const unnamed = []
  for (const el of interactives) {
    if (!accessibleName(el)) unnamed.push({ path: pathOf(el), tag: el.tagName.toLowerCase() })
  }

  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
    .filter(isRendered)
    .map((h) => ({ level: Number(h.tagName[1]), text: (h.textContent || '').trim().slice(0, 50) }))

  return {
    theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
    density: (document.querySelector('[data-density]') || {}).getAttribute
      ? document.querySelector('[data-density]').getAttribute('data-density')
      : null,
    counts: {
      elements: all.length,
      interactives: interactives.length,
      textNodes: null,
    },
    contrast: contrastFindings,
    unmeasurableBg,
    tapTargets: { floor: tapFloor, under: tapFindings, underWcagFloor: wcagFloorFindings },
    typeFloor: { floor: typeFloor, under: typeFindings },
    aria: {
      duplicateIds,
      tabs: tabWiring,
      tabpanels: panelWiring,
      landmarks,
      liveRegions,
      unnamedControls: unnamed,
      headings,
    },
  }
}
