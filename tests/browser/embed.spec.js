import { test, expect } from '@playwright/test'

for (const width of [320, 375, 768]) {
  test(`embed loads and keyboard works at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const failures = []
    page.on('pageerror', (error) => failures.push(error.message))
    await page.goto('/professor-guide/embed-test.html')
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Open Professor Guide full page' })).toBeFocused()
    const frame = page.frameLocator('iframe')
    await expect(frame.getByRole('heading', { name: 'Professor Guide', exact: true })).toBeVisible()
    await expect(frame.getByText(/registration sections collected/)).toBeVisible()
    const summary = frame.locator('summary').first()
    await summary.focus()
    await page.keyboard.press('Enter')
    await expect(frame.locator('details').first()).toHaveAttribute('open', '')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    const child = page.frames().find((item) => item.url().includes('?embed=1'))
    expect(await child.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    expect(failures).toEqual([])
  })
}

test('200 percent shell zoom retains content and focus', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1200 })
  await page.goto('/professor-guide/embed-test.html')
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  await expect(page.getByRole('link')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await expect(page.frameLocator('iframe').getByRole('heading', { name: 'Professor Guide', exact: true })).toBeVisible()
})

test('hash and query navigation keep data available', async ({ page }) => {
  await page.goto('/professor-guide/?course=CS374#preview')
  await expect(page.getByText(/registration sections collected/)).toBeVisible()
  const response = await page.request.get('/professor-guide/data/integration.json')
  expect(response.ok()).toBeTruthy()
})
