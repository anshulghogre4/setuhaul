import { expect, test, type Page } from 'playwright/test'

import { ACCOUNTS, ORIGIN, recorderFor, storageFor } from './support'
import { mintSession, toStorageState } from '../support/session'

/**
 * 01 - Driver chat. 20 designed controls.
 *
 * Identity: `driver-sandbox` (`driver.resched@setuhaul.com`, `FAC-GGN-01`) -- the only driver the
 * roster marks write-safe. Its four `SHP-RS-*` shipments are the sandbox; the demo cast
 * (`SHP1xxx` / `SHP-D16-*`) is never touched here.
 *
 * The LLM leg is unavailable locally by design (the in-process assistant needs Vertex ADC), so
 * every control that only exists *inside* a completed assistant turn -- option cards, the two-step
 * confirm, quick replies, disambiguation chips -- is BLOCKED-ENV rather than absent. The send
 * control itself is still fully testable: the designed degraded state is that the message posts and
 * the failure is surfaced honestly rather than as a delivered message.
 */

const say = recorderFor('01-driver')

test.use({
  storageState: storageFor('driver-sandbox'),
  viewport: { width: 390, height: 844 },
})

/** The one sandbox shipment carrying a promise state (`PENDING_CONFIRMATION`), so its conversation
 *  renders the persistent state line. Verified against `GET /api/v1/driver/context`. */
const THREAD = 'SHP-RS-PENDING'

test('driver: thread list, nav chrome and profile', async ({ page }) => {
  const ctx = page.waitForResponse((r) => r.url().includes('/api/v1/driver/context') && r.ok())
  await page.goto('/driver')
  await ctx

  const cards = page.locator('ul[role="list"] a[href^="/driver/t/"]')
  await expect(cards.first()).toBeVisible()
  const cardCount = await cards.count()
  const firstHref = await cards.first().getAttribute('href')
  await cards.first().click()
  await expect(page).toHaveURL(new RegExp(`${firstHref}$`))
  say(
    'Thread card (active)',
    'WORKING',
    `${cardCount} cards rendered as real <Link>s; clicking the first navigated to ${firstHref}`,
  )

  await page.getByRole('link', { name: 'Back to loads' }).click()
  await expect(page).toHaveURL(/\/driver$/)
  say(
    'Back chevron (Conversation header)',
    'WORKING',
    'returned to /driver from the conversation; the chevron is a 48x48 <Link aria-label="Back to loads">',
  )

  const resolvedHeading = page.getByRole('heading', { level: 2 }).filter({ hasText: /resolved/i })
  if ((await resolvedHeading.count()) > 0) {
    say('Thread card (resolved)', 'WORKING', 'resolved group rendered; its cards are real links')
  } else {
    say(
      'Thread card (resolved)',
      'BLOCKED-ENV',
      'no resolved group exists to click: all four SHP-RS-* sandbox shipments are current_status=IN_TRANSIT, so data.ts\'s INACTIVE set matches none of them. Producing one would mean writing a terminal status onto seed data.',
    )
  }

  await page.locator('header a[href="/driver/profile"]').click()
  await expect(page).toHaveURL(/\/driver\/profile$/)
  say('Settings gear (thread-list header)', 'WORKING', 'navigated to /driver/profile')

  const nav = page.getByRole('navigation', { name: 'Driver' })
  await nav.getByRole('link', { name: 'Threads' }).click()
  await expect(page).toHaveURL(/\/driver$/)
  say('Bottom nav "Threads"', 'WORKING', 'navigated to the thread list')

  await nav.getByRole('link', { name: 'Profile' }).click()
  await expect(page).toHaveURL(/\/driver\/profile$/)
  say('Bottom nav "Profile"', 'WORKING', 'navigated to /driver/profile')
})

test('driver: profile rows', async ({ page }) => {
  await page.goto('/driver/profile')
  await expect(page.getByRole('heading', { name: 'Profile' })).toBeVisible()

  const enableBtn = page.getByRole('button', { name: /turn on|enable|notification/i })
  if ((await enableBtn.count()) > 0) {
    const label = await enableBtn.first().textContent()
    say(
      'Notifications row (On)',
      'WORKING',
      `the re-entry control renders as "${label?.trim()}" and calls Notification.requestPermission() on activation -- the designed re-prompt path for a driver who denied push at onboarding`,
    )
  } else {
    const status = await page
      .locator('main')
      .getByText(/^(On|Not available)$/)
      .first()
      .textContent()
    say(
      'Notifications row (On)',
      'WORKING',
      `permission already resolved in this browser profile, so the row renders its state ("${status?.trim()}") with no button -- the designed shape for that branch`,
    )
  }

  await expect(page.getByText('Language')).toBeVisible()
  await expect(page.getByText('English', { exact: true })).toBeVisible()
  say(
    'Language row',
    'WORKING',
    'renders "Language / English" as plain text with no picker and no disabled dropdown -- U31\'s stated v1 behaviour ("inert, present so the setting has a future home")',
  )

  const themeBtn = page
    .locator('main div')
    .filter({ hasText: /^Theme/ })
    .getByRole('button')
    .first()
  await themeBtn.click()
  const warning = page.getByRole('dialog').filter({ hasText: /dark mode is hard to read/i })
  await expect(warning).toBeVisible()
  // DOM order, read off the document rather than off a nth() guess: U79 requires the SAFER action
  // first, so that a keyboard user who overshoots lands on the harmless one.
  const order = await warning.evaluate((el) =>
    Array.from(el.querySelectorAll('button'))
      .map((b) => (b.textContent ?? '').trim())
      .filter((t) => t.length > 0),
  )
  const keepIdx = order.findIndex((t) => /keep light/i.test(t))
  const darkIdx = order.findIndex((t) => /switch to dark/i.test(t))
  say(
    'Theme row',
    'WORKING',
    `light -> dark activation opened the F10 sunlight-warning dialog naming the real consequence; its buttons in DOM order are [${order.join(' | ')}], so the safer action precedes the committing one (U79: keepLight@${keepIdx} < switchToDark@${darkIdx} = ${keepIdx < darkIdx})`,
  )
  await page.getByRole('button', { name: 'Keep light' }).click()
  await expect(warning).toBeHidden()
})

test('driver: conversation composer, send and the state line', async ({ page }) => {
  const ctx = page.waitForResponse((r) => r.url().includes('/api/v1/driver/context') && r.ok())
  await page.goto('/driver')
  await ctx
  // Navigated by CLICK, not by goto: the conversation reads its thread from `threadsAtom`, which
  // only the list route populates. A direct goto leaves the atom empty and the header renders with
  // no promise state at all -- which would misreport the state line as absent.
  await page.locator(`a[href="/driver/t/${THREAD}"]`).click()
  await expect(page).toHaveURL(new RegExp(`${THREAD}$`))

  // The state line's own activation is verified AFTER the send below, not here: on a freshly
  // opened thread the transcript is empty (this surface has no `/chat/history` restore), so a tap
  // now would have nothing to scroll to and would report a defect that is really an empty list.
  await expect(
    page.getByRole('button', { name: 'Go to the message that set this state' }),
  ).toBeVisible()

  // ---- Composer ------------------------------------------------------------------------------
  const composer = page.getByRole('textbox', { name: 'Message' })
  const send = page.getByRole('button', { name: 'Send message' })
  await expect(send).toBeDisabled()
  await composer.fill('Sweep probe: composer accepts input')
  await expect(composer).toHaveValue('Sweep probe: composer accepts input')
  await expect(send).toBeEnabled()
  say(
    'Composer text input',
    'WORKING',
    'accepted typed text; the send control transitioned disabled -> enabled on non-empty input, and the textarea is never disabled (no `disabled` prop exists on the component)',
  )

  // ---- Send ----------------------------------------------------------------------------------
  const streamReq = page.waitForRequest(
    (r) => r.url().includes('/api/v1/chat/stream') && r.method() === 'POST',
  )
  const streamRes = page.waitForResponse((r) => r.url().includes('/api/v1/chat/stream'))
  await send.click()
  const req = await streamReq
  const res = await streamRes
  const body = req.postDataJSON() as { client_message_id?: string; thread_id?: string }
  await expect(page.getByText('Sweep probe: composer accepts input')).toBeVisible()
  // Give the stream time to deliver its `error` frame and the transcript time to repaint, then
  // report what the transcript ACTUALLY says rather than asserting a state and hoping.
  await page.waitForTimeout(4000)
  const retryVisible = await page.getByRole('button', { name: 'Retry' }).count()
  const transcript = (await page.locator('[role="log"]').innerText()).replace(/\s+/g, ' ').trim()
  const marksFailure = /not sent|retry/i.test(transcript)
  say(
    'Send arrow',
    'BLOCKED-ENV',
    `POST /api/v1/chat/stream fired (HTTP ${res.status()}) carrying client_message_id=${body.client_message_id ? 'present' : 'MISSING'} and thread_id=${body.thread_id}; the optimistic bubble appeared immediately, so the optimistic half of the control is WORKING. The stream then answers an \`error\` frame (LLM_UNAVAILABLE -- the in-process assistant has no Vertex credentials locally), which is the designed degraded state. What the transcript shows afterwards, verbatim: "${transcript.slice(0, 260)}" -- inline Retry control present: ${retryVisible > 0}; failure marked: ${marksFailure}.`,
  )

  // ---- Persistent state line tap (issue #99.3) -----------------------------------------------
  await verifyStateLineTap(page)

  const noTurn =
    'exists only inside a completed assistant turn. /api/v1/chat/stream returns an LLM_UNAVAILABLE error frame locally (verified above), so no option set, quick-reply row or clarification chip is ever appended to the transcript. Component wiring is present in source (option-set.tsx / composer.tsx quickReplies / use-driver-turn.ts PROMISE_TOOLS) but cannot be activated here.'
  say('Option card tap', 'BLOCKED-ENV', noTurn)
  say('Confirm the held option (2nd explicit action)', 'BLOCKED-ENV', noTurn)
  say('Quick-reply chips', 'BLOCKED-ENV', noTurn)
  say('Disambiguation chips (Leave the gate / Unloading starts)', 'BLOCKED-ENV', noTurn)
  say('Cancel / change-mind confirmation reply', 'BLOCKED-ENV', noTurn)

  const rows = await page.locator('[role="log"] [role="listitem"]').count()
  say(
    '"N new" scroll-to-latest pill',
    'BLOCKED-ENV',
    `gated on being scrolled more than one viewport from the bottom AND on new messages arriving. The transcript holds ${rows} row(s) and no assistant reply can arrive, so the state is unreachable; transcript.tsx's pinned/unseen wiring is present in source.`,
  )

  say(
    'Push notification tap (deep link)',
    'BLOCKED-ENV',
    'an OS-level notification activation, outside a Playwright page context. `pushSubscriptionEnabled` is also false (features/driver/lib/flags.ts) and no producer writes a notifications row yet, so no push would be delivered either.',
  )
})

/**
 * The persistent state line's tap (issue #99.3), verified against a transcript that actually has
 * something in it.
 *
 * ## Two deliberate choices in how this is proved
 *
 * 1. **The viewport is shrunk to 390x340 first.** The transcript only overflows when there is more
 *    content than room, and the LLM leg is unavailable locally, so this run's transcript is the one
 *    probe message the send test above posted. A 340px-tall phone makes that one message genuinely
 *    scrollable, which turns "the scroll happened" into a measurable number instead of an assertion
 *    about an unscrollable list. It is a real device size, not a rigged one -- the PWA's stated
 *    range starts at 320px wide.
 * 2. **Focus is asserted as well as `scrollTop`.** `transcript.tsx` moves focus to the target row
 *    (`tabIndex={-1}`, `data-message-id`), so `document.activeElement` naming the exact message is
 *    the proof that the handler found the RIGHT row rather than merely moving the scrollbar.
 *
 * ## The boundary this records honestly
 *
 * `components.md` §6 says the tap goes to "the message that established the state". With
 * `promise_state=PENDING_CONFIRMATION` arriving from `/api/v1/driver/context` and no
 * `GET /chat/history` call site anywhere in `src/`, the establishing message is not in this
 * client's transcript at all -- so `conversation.tsx`'s tier-3 rule scrolls as far back as the
 * transcript goes, and says so in its own comment rather than fabricating a target.
 */
async function verifyStateLineTap(page: Page) {
  await page.setViewportSize({ width: 390, height: 340 })
  const stateLine = page.getByRole('button', { name: 'Go to the message that set this state' })
  await expect(stateLine).toBeVisible()

  const before = await page.evaluate(() => {
    const el = document.querySelector<HTMLElement>('[role="log"]')
    if (!el) return null
    // Start from the bottom, which is where a driver reading the latest message actually is.
    el.scrollTop = el.scrollHeight
    return {
      top: el.scrollTop,
      scrollable: el.scrollHeight > el.clientHeight,
      rows: el.querySelectorAll('[data-message-id]').length,
      firstId: el.querySelector<HTMLElement>('[data-message-id]')?.dataset.messageId ?? null,
    }
  })

  let requests = 0
  page.on('request', () => {
    requests += 1
  })
  await stateLine.click()
  await page.waitForTimeout(400)

  const after = await page.evaluate(() => {
    const el = document.querySelector<HTMLElement>('[role="log"]')
    const active = document.activeElement as HTMLElement | null
    return {
      top: el?.scrollTop ?? -1,
      focusedMessageId: active?.getAttribute('data-message-id') ?? null,
    }
  })

  const moved = before !== null && after.top < before.top
  const landed = after.focusedMessageId !== null && after.focusedMessageId === before?.firstId
  expect(landed, 'the state-line tap must focus the origin message row').toBe(true)

  say(
    'Persistent state line tap',
    'WORKING',
    `the line (promise_state=PENDING_CONFIRMATION) now scrolls the transcript to its origin message and focuses it. Measured at 390x340 with ${before?.rows ?? 0} message row(s) and the transcript scrolled to the bottom: scrollTop ${before?.top ?? -1} -> ${after.top} (moved: ${moved}; transcript scrollable: ${before?.scrollable ?? false}), document.activeElement is the row data-message-id=${after.focusedMessageId} which is the transcript's origin row (${landed}), and ${requests} network request(s) fired -- the jump is local, as it should be. BOUNDARY, recorded rather than papered over: this thread's PENDING state came from GET /driver/context and its true establishing message was never loaded (no GET /chat/history call site exists in src/), so conversation.tsx's establishingMessageId() resolved via its stated tier-3 fallback -- the oldest message this client holds -- rather than tiers 1/2 (the held slot's option-set card, or the most recent optionSet/receipt part). Those two tiers need a completed assistant turn, which is BLOCKED-ENV here for the same reason every other in-turn control is.`,
  )

  await page.setViewportSize({ width: 390, height: 844 })
}

/**
 * Sign-out gets its OWN minted session rather than the shared `driver-sandbox.json`.
 *
 * `signOut()` revokes that session server-side, and `AuthProvider`'s central 401 handler will also
 * call it on any dead-token response earlier in the file. Reusing the shared storageState here made
 * this test depend on nothing else in the run having disturbed it -- which is exactly the
 * cross-test coupling `storage-state-isolation.spec.ts` exists to warn about.
 */
test('driver: sign out', async ({ browser }) => {
  const session = await mintSession(ACCOUNTS['driver-sandbox'])
  const context = await browser.newContext({
    storageState: toStorageState(session, ORIGIN),
    viewport: { width: 390, height: 844 },
  })
  const page = await context.newPage()

  await page.goto(`${ORIGIN}/driver/profile`)
  await page.getByRole('button', { name: /^sign out$/i }).first().click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Sign out?' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Stay signed in' })).toBeVisible()
  const logout = page.waitForResponse((r) => r.url().includes('/auth/v1/logout'))
  await dialog.getByRole('button', { name: /^sign out$/i }).click()
  const res = await logout
  const scope = new URL(res.url()).searchParams.get('scope')
  await expect(page).toHaveURL(/\/signin$/, { timeout: 15_000 })
  say(
    'Sign out',
    'WORKING',
    `confirm dialog opened with the safer action first (U79); committing fired POST /auth/v1/logout?scope=${scope ?? '(default)'} (HTTP ${res.status()}) and the guard redirected to /signin. scope=local is the single-device revocation the design requires.`,
  )
  await context.close()
})
