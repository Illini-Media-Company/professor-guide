// Resolve one coherent manifest. The search index avoids downloading raw archives.
export const DATA_BASE = `${import.meta.env.BASE_URL}data/`

export async function readObject(entry, signal) {
  if (entry?.status !== 'available' || !/^objects\/[a-f0-9]{64}\.json$/.test(entry.path) || entry.path !== `objects/${entry.sha256}.json`) {
    throw new Error('This data file is unavailable or unsupported.')
  }
  const response = await fetch(`${DATA_BASE}${entry.path}`, { signal })
  if (!response.ok) throw new Error(`Guide data could not be loaded (${response.status}).`)
  const bytes = await response.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const hash = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
  if (entry.bytes !== bytes.byteLength || entry.sha256 !== hash) {
    throw new Error('The data download was incomplete. Please try again.')
  }
  return JSON.parse(new TextDecoder().decode(bytes))
}

export async function loadGuide(signal) {
  const response = await fetch(`${DATA_BASE}integration.json`, { signal })
  if (!response.ok) throw new Error(`The guide could not be loaded (${response.status}).`)
  const manifest = await response.json()
  if (manifest.schema_version !== 1 || manifest.dataset !== 'professor_guide' || manifest.data_kind !== 'live') {
    throw new Error('The guide data is unavailable or unsupported.')
  }
  if (!manifest.files?.guide) return { manifest, index: null }
  const index = await readObject(manifest.files.guide, signal)
  if (![1, 2].includes(index?.schema_version) || index.dataset !== 'guide_index' || index.data_kind !== 'live' ||
      !Array.isArray(index.professors) || !Array.isArray(index.courses) || !Array.isArray(index.grade_records) ||
      !Array.isArray(index.terms) || !Array.isArray(index.gpa_sources) || !index.coverage ||
      (index.schema_version === 2 && !Array.isArray(index.schedule_names)) ||
      index.professors.some((person) => !Array.isArray(person.courses) || !Array.isArray(person.faculty_links))) {
    throw new Error('The guide index is unavailable or unsupported.')
  }
  return { manifest, index }
}
