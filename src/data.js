// Resolve one manifest's files under Vite's GitHub Pages base.
const DATA_BASE = `${import.meta.env.BASE_URL}data/`

async function readJson(path, signal) {
  const response = await fetch(`${DATA_BASE}${path}`, { signal })
  if (!response.ok) throw new Error(`Course data could not be loaded (${response.status}).`)
  return response.json()
}

export async function loadGuide(signal) {
  const manifest = await readJson('integration.json', signal)
  const schedule = manifest.files?.schedule
  if (
    manifest.schema_version !== 1 || manifest.dataset !== 'professor_guide' ||
    schedule?.status !== 'available' || !/^objects\/[a-f0-9]{64}\.json$/.test(schedule.path)
  ) {
    throw new Error('This data manifest is not supported by the starter.')
  }
  const data = await readJson(schedule.path, signal)
  if (
    data.schema_version !== 1 || data.dataset !== 'course_explorer' ||
    !['live', 'development_fixture'].includes(data.data_kind) ||
    !Array.isArray(data.courses) || !Array.isArray(data.sections) ||
    !Array.isArray(data.relationships) || data.term?.id !== manifest.current_term?.id
  ) {
    throw new Error('This data version is not supported by the starter.')
  }
  return { manifest, schedule: data }
}
