import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import { createHash } from 'node:crypto'
import { summarizeGrades } from '../../src/guide.js'

const manifest = JSON.parse(fs.readFileSync('public/data/integration.json', 'utf8'))
const index = JSON.parse(fs.readFileSync(`public/data/${manifest.files.guide.path}`, 'utf8'))
const coursePerson = index.professors.find((p) => p.professor_id === 'prof_0001')
const rated = index.professors.find((p) => p.rmp?.overall_quality != null && p.courses.length)
const pending = index.professors.find((p) => !p.rmp && p.courses.length)
const resultCount = (index.professors.length + (index.schedule_names?.length || 0)).toLocaleString('en-US')
const searchAndSelect = async (page, person) => {
  await page.getByRole('searchbox', { name: 'Search', exact: true }).fill(person.display_name)
  await page.getByRole('button', { name: person.display_name, exact: false }).first().click()
  await expect(page.getByRole('heading', { name: person.display_name, exact: true })).toBeVisible()
}

for (const width of [320, 375, 768, 1100]) {
  test(`iframe search, detail and back navigation work at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const failures = []
    page.on('pageerror', (error) => failures.push(error.message))
    await page.goto('/professor-guide/embed-test.html')
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'Open Professor Guide full page' })).toBeFocused()
    const frame = page.frameLocator('iframe')
    await expect(frame.getByRole('heading', { name: 'Professor Guide', exact: true })).toBeVisible()
    await frame.getByRole('searchbox').fill(rated.display_name)
    const choice = frame.getByRole('button', { name: rated.display_name, exact: false }).first()
    await choice.focus()
    await page.keyboard.press('Enter')
    await expect(frame.getByRole('heading', { name: rated.display_name, exact: true })).toBeFocused()
    await expect(frame.getByRole('heading', { name: 'Student ratings' })).toBeVisible()
    await expect(frame.locator('.ratings-grid')).toContainText(rated.rmp.overall_quality.toFixed(1))
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    const child = page.frames().find((item) => item.url().includes('?embed=1'))
    expect(await child.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    if (width < 900) await expect(frame.getByRole('searchbox')).toBeHidden()
    await frame.getByRole('button', { name: 'Back to results' }).click()
    await expect(frame.getByRole('searchbox')).toBeVisible()
    await expect(choice).toBeFocused()
    expect(failures).toEqual([])
  })
}

test('pending ratings do not exclude instructors or turn into zero scores', async ({ page }) => {
  await page.goto('/professor-guide/')
  await searchAndSelect(page, pending)
  await expect(page.locator('.ratings-grid .pending')).toHaveCount(4)
  await expect(page.locator('.ratings-grid')).not.toContainText('0 / 5')
  await expect(page.getByText('Verified RMP data is pending.')).toBeVisible()
})

test('per-course GPA agrees with source weights and semester changes leave RMP professor-wide', async ({ page }) => {
  await page.goto('/professor-guide/')
  await searchAndSelect(page, coursePerson)
  const originalRatings = await page.locator('.ratings-grid').textContent()
  await page.getByRole('combobox', { name: 'Course', exact: true }).selectOption('SOC 225')
  const rows = index.grade_records.filter((g) => g.professor_id === coursePerson.professor_id && g.course_code === 'SOC 225')
  await expect(page.locator('.gpa-number')).toContainText(summarizeGrades(rows).gpa.toFixed(2))
  await page.getByRole('combobox', { name: 'Semester', exact: true }).selectOption('2025-fall')
  // Filtering closes the panel; select the filtered instructor again.
  await page.getByRole('button', { name: coursePerson.display_name, exact: false }).first().click()
  await page.getByRole('combobox', { name: 'Course', exact: true }).selectOption('SOC 225')
  await expect(page.locator('.gpa-number')).toContainText(summarizeGrades(rows.filter((r) => r.term_id === '2025-fall')).gpa.toFixed(2))
  await expect(page.locator('.ratings-grid')).toHaveText(originalRatings)
  await page.getByText('View semester data', { exact: false }).click()
  await expect(page.locator('.history-table tbody tr')).toHaveCount(1)
})

test('course search supports compact codes and opens connected instructor details', async ({ page }) => {
  await page.goto('/professor-guide/')
  await page.getByRole('combobox', { name: 'Search for', exact: true }).selectOption('courses')
  await page.getByRole('searchbox').fill('SOC225')
  await page.getByRole('button', { name: 'SOC 225', exact: false }).first().click()
  await expect(page.getByRole('heading', { name: 'SOC 225', exact: true })).toBeVisible()
  await page.locator('.course-people-table').getByRole('button', { name: coursePerson.display_name, exact: false }).click()
  await expect(page.getByRole('heading', { name: coursePerson.display_name, exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Course', exact: true })).toHaveValue('SOC 225')
})

test('ECE 374 and Emily Fox are available without GPA, and existing RMP data is retained', async ({ page }) => {
  await page.goto('/professor-guide/')
  await page.getByRole('combobox', { name: 'Search for', exact: true }).selectOption('courses')
  await page.getByRole('searchbox').fill('ECE374')
  await page.getByRole('combobox', { name: 'Semester', exact: true }).selectOption('2026-fall')
  await page.getByRole('button', { name: 'ECE 374', exact: false }).first().click()
  await expect(page.getByRole('heading', { name: 'ECE 374', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Emily Kyle Fox', exact: false }).click()
  await expect(page.getByRole('heading', { name: 'Emily Kyle Fox', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Course', exact: true })).toHaveValue('ECE 374')
  const emily = index.professors.find((p) => p.professor_id === 'prof_uiuc_ekfox')
  await expect(page.locator('.ratings-grid')).toContainText(emily.rmp.overall_quality.toFixed(1))
  await expect(page.locator('.gpa-number')).toHaveText('Pending')
  await expect(page.getByRole('combobox', { name: 'Course', exact: true }).locator('option')).toContainText(['CS 374', 'ECE 374'])
})

test('unverified source names remain searchable with identity and metric states pending', async ({ page }) => {
  const raw = index.schedule_names.find((e) => e.display_name === 'Fox, E' && e.subject === 'CS')
  await page.goto(`/professor-guide/#view=professors&person=${raw.entry_id}&course=CS+374`)
  await expect(page.getByRole('heading', { name: 'Fox, E', exact: true })).toBeVisible()
  await expect(page.getByText('Schedule name · identity pending')).toBeVisible()
  await expect(page.getByText(/same abbreviation may refer to different people/)).toBeVisible()
  await expect(page.locator('.ratings-grid .pending')).toHaveCount(4)
  await expect(page.locator('.gpa-number')).toHaveText('Pending')
  await page.getByText('Teaching history', { exact: true }).click()
  await expect(page.locator('.teaching-terms p')).not.toBeEmpty()
})

test('initial browsing includes everyone with rated instructors first; pagination and clearing restore that list', async ({ page }) => {
  await page.goto('/professor-guide/')
  await expect(page.getByRole('status')).toContainText(`${resultCount} results`)
  await expect(page.getByRole('heading', { name: 'Professors', exact: true })).toBeVisible()
  const expected = index.professors.filter((p) => p.rmp?.overall_quality != null).sort((a, b) => a.display_name.split(' ').at(-1).localeCompare(b.display_name.split(' ').at(-1)) || a.display_name.localeCompare(b.display_name)).slice(0, 10).map((p) => p.display_name)
  await expect(page.locator('.result-link strong')).toHaveText(expected)
  await expect(page.locator('.results-table .pending')).toHaveCount(0)
  await page.getByRole('button', { name: 'Next results page' }).click()
  await expect(page.locator('.pagination')).toContainText('11–20')
  await page.getByRole('searchbox').fill('no-such-instructor-987654321')
  await expect(page.getByRole('heading', { name: 'No results found' })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await expect(page.getByRole('status')).toContainText(`${resultCount} results`)
  await expect(page.locator('.pagination')).toContainText('1–10')
})

test('subject and semester browsing keep rated instructors first without hiding pending listings', async ({ page }) => {
  await page.goto('/professor-guide/')
  const entries = [...index.professors, ...(index.schedule_names || [])]
  const subject = 'CS'
  const term = '2025-fall'
  const alphabetical = (a, b) => a.display_name.split(' ').at(-1).localeCompare(b.display_name.split(' ').at(-1)) || a.display_name.localeCompare(b.display_name)
  const check = async (selectedSubject, selectedTerm) => {
    const matches = entries.filter((p) => p.courses.some((c) => (!selectedSubject || c.course_code.split(' ')[0] === selectedSubject) && (!selectedTerm || c.term_ids.includes(selectedTerm))))
    expect(matches.some((p) => p.rmp?.overall_quality == null)).toBeTruthy()
    const ordered = [...matches].sort((a, b) => Number(b.rmp?.overall_quality != null) - Number(a.rmp?.overall_quality != null) || alphabetical(a, b))
    await expect(page.getByRole('status')).toContainText(`${matches.length.toLocaleString('en-US')} results`)
    await expect(page.locator('.result-link strong')).toHaveText(ordered.slice(0, 10).map((p) => p.display_name))
  }
  await page.getByRole('combobox', { name: 'Subject', exact: true }).selectOption(subject)
  await check(subject, '')
  await page.getByRole('combobox', { name: 'Semester', exact: true }).selectOption(term)
  await check(subject, term)
  await page.getByRole('combobox', { name: 'Subject', exact: true }).selectOption('')
  await check('', term)
})

test('selection and filters survive reload and browser Back', async ({ page }) => {
  await page.goto('/professor-guide/?embed=1')
  await searchAndSelect(page, coursePerson)
  await page.getByRole('combobox', { name: 'Course', exact: true }).selectOption('SOC 225')
  await page.reload()
  await expect(page.getByRole('heading', { name: coursePerson.display_name, exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Course', exact: true })).toHaveValue('SOC 225')
  const fullPage = new URL(await page.getByRole('link', { name: 'Open full page' }).getAttribute('href'))
  expect(fullPage.searchParams.has('embed')).toBeFalsy()
  expect(fullPage.hash).toContain('person=prof_0001')
  await page.goBack()
  await expect(page.getByRole('searchbox')).toHaveValue(coursePerson.display_name)
})

test('the browser loads just one compact index rather than raw archive or identity files', async ({ page }) => {
  const requests = []
  page.on('request', (request) => {
    if (request.url().includes('/data/')) requests.push(new URL(request.url()).pathname)
  })
  await page.goto('/professor-guide/')
  await expect(page.getByRole('status')).toContainText(`${resultCount} results`)
  expect(requests).toEqual(['/professor-guide/data/integration.json', `/professor-guide/data/${manifest.files.guide.path}`])
  await page.getByText('About the data', { exact: false }).click()
  await expect(page.getByRole('link', { name: 'Current schedule JSON' })).toBeVisible()
})

test('a missing index shows a recoverable loading error', async ({ page }) => {
  await page.route(`**/data/${manifest.files.guide.path}`, (route) => route.fulfill({ status: 404, body: 'Missing object' }))
  await page.goto('/professor-guide/')
  await expect(page.getByRole('alert')).toContainText('404')
  await page.unroute(`**/data/${manifest.files.guide.path}`)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('searchbox')).toBeVisible()
})

test('corrupt index bytes fail closed instead of mixing data generations', async ({ page }) => {
  await page.route(`**/data/${manifest.files.guide.path}`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...index, coverage: {} }) }))
  await page.goto('/professor-guide/')
  await expect(page.getByRole('alert')).toContainText('incomplete')
  await expect(page.getByRole('searchbox')).toHaveCount(0)
})

test('older manifests with pending inputs show a preparation state', async ({ page }) => {
  const older = structuredClone(manifest)
  delete older.files.guide
  await page.route('**/data/integration.json', (route) => route.fulfill({ json: older }))
  await page.goto('/professor-guide/')
  await expect(page.getByRole('heading', { name: 'Search data is pending.' })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('an unsupported index with valid hashes shows an error instead of crashing the interface', async ({ page }) => {
  const modified = structuredClone(index)
  delete modified.terms
  const body = JSON.stringify(modified)
  const hash = createHash('sha256').update(body).digest('hex')
  const adjusted = structuredClone(manifest)
  adjusted.files.guide = { ...manifest.files.guide, path: `objects/${hash}.json`, sha256: hash, bytes: Buffer.byteLength(body) }
  await page.route('**/data/integration.json', (route) => route.fulfill({ json: adjusted }))
  await page.route(`**/data/objects/${hash}.json`, (route) => route.fulfill({ body, contentType: 'application/json' }))
  await page.goto('/professor-guide/')
  await expect(page.getByRole('alert')).toContainText('unsupported')
  await expect(page.getByRole('searchbox')).toHaveCount(0)
})

test('zero percent take-again is displayed as a genuine value', async ({ page }) => {
  const modified = structuredClone(index)
  modified.professors.find((p) => p.professor_id === rated.professor_id).rmp.would_take_again_percent = 0
  const body = JSON.stringify(modified)
  const hash = createHash('sha256').update(body).digest('hex')
  const adjusted = structuredClone(manifest)
  adjusted.files.guide = { ...manifest.files.guide, path: `objects/${hash}.json`, sha256: hash, bytes: Buffer.byteLength(body) }
  await page.route('**/data/integration.json', (route) => route.fulfill({ json: adjusted }))
  await page.route(`**/data/objects/${hash}.json`, (route) => route.fulfill({ body, contentType: 'application/json' }))
  await page.goto('/professor-guide/')
  await searchAndSelect(page, rated)
  await expect(page.locator('.ratings-grid')).toContainText('0%')
})

test('200 percent zoom retains search, detail and keyboard access without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1200 })
  await page.goto('/professor-guide/')
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  await searchAndSelect(page, rated)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.getByRole('button', { name: 'Back to results' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('searchbox')).toBeVisible()
})
