// The two UI actions T18 does not reach: cancelling a running agent run, and revoking a remembered
// rejection. Same real stack as T18 (playwright.config.ts). These tests use other campaigns and
// assert only relative behaviour, so they hold whether or not T18 ran first on the same graph.
import { expect, test, type Locator, type Page } from '@playwright/test'

function liveStatus(page: Page): Locator {
  return page.locator('.conversation [aria-live="polite"]')
}

function candidateRow(page: Page, name: string): Locator {
  return page.locator('table[aria-label="Replacement candidates"] tbody tr', { hasText: name })
}

async function ruleCheck(page: Page) {
  const done = page.waitForResponse((r) => r.url().includes('/evaluate') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Rule check (no AI)' }).click()
  expect((await done).status()).toBe(200)
  await expect(page.getByText('Rule check — no AI run')).toBeVisible()
}

test('Cancel run stops a running agent run, stages nothing and offers a retry', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('combobox', { name: /Campaign/ }).selectOption('camp_02')
  await page.getByRole('button', { name: 'Run agent', exact: true }).click()
  await expect(liveStatus(page)).toHaveText(/^Running/, { timeout: 60_000 })

  await page.getByRole('button', { name: 'Cancel run' }).click()
  await expect(liveStatus(page)).toHaveText('Cancelled', { timeout: 30_000 })
  await expect(page.getByText('Run cancelled.')).toBeVisible()
  await expect(page.locator('.conversation')).toContainText('Nothing was approved.')
  await expect(page.getByRole('button', { name: 'Retry' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Run agent', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Review proposal' })).toHaveCount(0)
})

test('An edit opened before another change can neither overwrite it nor crash on a cleared date', async ({ page, context }) => {
  // Review fix C2 and C4, on a window T18 does not use.
  const openEditor = async (p: Page) => {
    await p.goto('/')
    await p.getByRole('tab', { name: 'Demo data' }).click()
    await p.getByRole('button', { name: 'Edit avail_cr05' }).click()
  }
  await openEditor(page)
  await page.getByLabel('End (IST)').fill('')
  await expect(page.getByText('Enter a complete end date and time.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save new version' })).toBeDisabled()
  await page.getByLabel('End (IST)').fill('2026-10-24T20:30')
  await page.getByLabel(/^Reason for the edit/).fill('Tab A edit (e2e).')
  await expect(page.getByRole('button', { name: 'Save new version' })).toBeEnabled()

  // Another tab saves a change to the same window first.
  const other = await context.newPage()
  await openEditor(other)
  await other.getByLabel('Status').selectOption('unavailable')
  await other.getByLabel(/^Reason for the edit/).fill('Tab B edit (e2e).')
  await other.getByRole('button', { name: 'Save new version' }).click()
  await expect(other.getByText('New source version saved.')).toBeVisible()

  // Tab A learns of the new revision by polling and refuses to save over it.
  await expect(page.getByText('This information changed after you opened the editor.')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: 'Save new version' })).toBeDisabled()
  await page.getByRole('button', { name: 'Reload current values' }).click()
  await expect(page.getByLabel('Status')).toHaveValue('unavailable')
  await expect(page.getByText('This information changed after you opened the editor.')).toBeHidden()
})

test('Revoking a rejection keeps it in history and restores the creator', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('combobox', { name: /Campaign/ }).selectOption('camp_03')
  await ruleCheck(page)
  const first = page.locator('table[aria-label="Replacement candidates"] tbody tr', { has: page.getByLabel('Rank 1', { exact: true }) })
  const name = (await first.locator('.name').textContent())!.trim()

  // Reject the top-ranked creator for this campaign only.
  await page.getByRole('button', { name: `Reject ${name}` }).click()
  const dialog = page.getByRole('dialog', { name: `Reject ${name}` })
  await dialog.getByLabel(/^Reason/).fill('Revocation check (e2e).')
  await dialog.getByRole('button', { name: 'Save rejection' }).click()
  await expect(dialog).toBeHidden()
  await ruleCheck(page)
  await expect(candidateRow(page, name)).toContainText('Excluded by your rejection')

  // Revoke it from Decision history: the record stays, its effect ends.
  await page.getByRole('tab', { name: /Decision history/ }).click()
  const rejection = page.locator('.event', { hasText: `Rejected ${name} for this campaign` })
  await rejection.getByRole('button', { name: 'Revoke rejection' }).click()
  await rejection.getByLabel('Reason for revoking').fill('Changed our mind (e2e).')
  await rejection.getByRole('button', { name: 'Confirm revoke' }).click()
  await expect(rejection.locator('.chip')).toHaveText('Revoked')
  await expect(page.locator('.event', { hasText: `Revoked the rejection of ${name}` })).toBeVisible()

  await page.getByRole('tab', { name: /Candidates/ }).click()
  await ruleCheck(page)
  await expect(candidateRow(page, name)).not.toContainText('Excluded by your rejection')
  await expect(candidateRow(page, name)).toContainText('Eligible')
})
