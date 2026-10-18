// T18 (ACCEPTANCE_TESTS): campaign → request → evidence → reject → new session → changed result →
// proposal → approve, in a real browser at 1280×720 against the real local model and FalkorDB.
// Everything asserted comes from the backend: rankings from graph evidence, drafts from the agent's
// tool calls, the approval from the saved decision. Nothing here is mocked.
import { expect, test, type Locator, type Page } from '@playwright/test'

const RUN_TIMEOUT = 300_000 // a cold model load plus one complete agent run

function liveStatus(page: Page): Locator {
  return page.locator('.conversation [aria-live="polite"]')
}

async function runAgent(page: Page, start: () => Promise<void>) {
  await start()
  await expect(liveStatus(page)).toHaveText(/^(Queued|Running)/, { timeout: 30_000 })
  await expect(liveStatus(page)).toHaveText(/^(Completed|Needs clarification|Failed|Cancelled|Interrupted)/, { timeout: RUN_TIMEOUT })
  await expect(liveStatus(page)).toHaveText('Completed')
}

function rankOne(page: Page): Locator {
  return page.locator('table[aria-label="Replacement candidates"] tbody tr', { has: page.getByLabel('Rank 1', { exact: true }) })
}

/** True while focus is inside the open modal dialog (or momentarily on the body between cycles). */
function focusStaysInDialog(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const dialog = document.querySelector('dialog[open]')
    const el = document.activeElement
    return !!dialog && (el === document.body || dialog.contains(el))
  })
}

test('T18: replacement flow with memory, a demo edit and a human approval', async ({ page }) => {
  const pageErrors: string[] = []
  page.on('pageerror', (e) => pageErrors.push(e.message))

  await page.goto('/')
  await expect(page.getByRole('note', { name: /Synthetic demo data/ })).toContainText('As of 15 Oct 2026')
  await expect(page.locator('.pill', { hasText: 'FalkorDB connected' })).toBeVisible()
  await expect(page.locator('.pill', { hasText: 'Model qwen3' })).toBeVisible()

  // 1. Campaign.
  await page.getByRole('combobox', { name: /Campaign/ }).selectOption('camp_01')
  await expect(page.getByRole('heading', { name: 'Luma Autumn Launch' })).toBeVisible()
  await expect(page.getByText('Open. Drafts are not approvals.')).toBeVisible()

  // Keyboard: Tab from the top of the page reaches "Run agent", and Enter starts the run.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  let reachedRun = false
  for (let i = 0; i < 25 && !reachedRun; i++) {
    await page.keyboard.press('Tab')
    reachedRun = await page.evaluate(() => document.activeElement?.textContent?.trim() === 'Run agent')
  }
  expect(reachedRun).toBe(true)

  // 2. Request: the local model chooses the tools; code ranks from graph evidence.
  await runAgent(page, () => page.keyboard.press('Enter'))
  await expect(page.getByText(/^Agent run run_/)).toBeVisible()
  await expect(rankOne(page)).toContainText('Mira Vale')
  const firstAnswer = page.locator('.msg.assistant').last()
  await expect(firstAnswer).toContainText('Mira Vale (cr_02)')
  await expect(firstAnswer).toContainText('not approved')
  await expect(page.getByRole('button', { name: 'Review proposal' })).toBeEnabled()

  // 3. Evidence: Tara's competitor conflict is a labelled graph path.
  await page.getByRole('button', { name: 'View evidence for Tara Reed' }).click()
  const drawer = page.getByRole('dialog', { name: /Tara Reed/ })
  await expect(drawer).toBeVisible()
  await drawer.getByRole('tab', { name: /Graph paths/ }).click()
  const conflictPath = drawer.locator('figure').first()
  await expect(conflictPath).toContainText('explains the result')
  await expect(conflictPath).toContainText('Noro Glow')
  await expect(conflictPath).toContainText('COMPETES_WITH')
  // Keyboard: Escape closes the drawer and focus returns to the row action.
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(page.getByRole('button', { name: 'View evidence for Tara Reed' })).toBeFocused()

  // 4. Reject Mira for this campaign only (the default scope).
  await page.getByRole('button', { name: 'Reject Mira Vale' }).click()
  const reject = page.getByRole('dialog', { name: 'Reject Mira Vale' })
  await expect(reject.getByLabel(/This campaign only/)).toBeChecked()
  await expect(reject.getByLabel(/^Reason/)).toBeFocused()
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab')
    expect(await focusStaysInDialog(page)).toBe(true)
  }
  await reject.getByLabel(/^Reason/).fill('Client wants a different voice for this launch (e2e).')
  await reject.getByRole('button', { name: 'Save rejection' }).click()
  await expect(reject).toBeHidden()
  // The memory change makes the shown result stale, so its draft cannot be approved.
  await expect(page.getByText('Information changed — run again.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Review proposal' })).toBeDisabled()

  // 5. New session: the rejection is a saved decision, not conversation text, so it still applies.
  await page.getByRole('button', { name: 'New session' }).click()
  await expect(page.locator('.msg')).toHaveCount(0)
  await runAgent(page, () => page.getByRole('button', { name: 'Run agent', exact: true }).click())
  await expect(rankOne(page)).toContainText('Noor Finch')
  await expect(page.getByRole('row', { name: /Mira Vale/ })).toContainText('Excluded by your rejection')

  // 6. Demo edit: Tara's Noro Glow agreement now ends before the delivery window.
  await page.getByRole('tab', { name: 'Demo data' }).click()
  await page.getByRole('button', { name: 'Edit agr_cr03' }).click()
  await page.getByLabel('End (IST)').fill('2026-10-19T23:59:59')
  await expect(page.locator('.diff')).toContainText('19 Oct 2026, 23:59:59 IST')
  await page.getByLabel(/^Reason for the edit/).fill('Agreement shortened for the demo (e2e).')
  await page.getByRole('button', { name: 'Save new version' }).click()
  await expect(page.getByText('New source version saved.')).toBeVisible()
  await page.getByRole('tab', { name: /Candidates/ }).click()
  await expect(page.getByText('Information changed — run again.')).toBeVisible()

  // 7. Run again: Tara now leads and the agent stages her draft.
  await runAgent(page, () => page.getByRole('button', { name: 'Run agent again' }).click())
  await expect(page.getByText('Information changed — run again.')).toBeHidden()
  await expect(rankOne(page)).toContainText('Tara Reed')

  // 8. Human approval: the backend revalidates and saves; the UI shows only its answer.
  await rankOne(page).getByRole('button', { name: 'Review proposal' }).click()
  const proposal = page.getByRole('dialog', { name: 'Review replacement proposal' })
  await expect(proposal).toContainText('Tara Reed')
  await expect(proposal.locator('dd .chip')).toContainText('Current')
  await expect(proposal).toContainText('Approves an internal replacement proposal. Does not contact or book the creator.')
  await proposal.getByRole('button', { name: 'Approve proposal' }).click()
  await expect(proposal.getByText('Approved and saved.')).toBeVisible()
  await proposal.locator('.dialog-foot').getByRole('button', { name: 'Close' }).click()
  await expect(proposal).toBeHidden()
  await expect(page.getByText(/Filled by approved proposal for Tara Reed/)).toBeVisible()

  // History keeps both explicit operator decisions.
  await page.getByRole('tab', { name: /Decision history/ }).click()
  await expect(page.getByText(/Approved the replacement proposal for Tara Reed/)).toBeVisible()
  await expect(page.getByText(/Rejected Mira Vale for this campaign/)).toBeVisible()

  expect(pageErrors).toEqual([])
})
