// All URLs follow the GitHub Pages repository base. Large term files load on demand.
export const DATA_BASE = `${import.meta.env.BASE_URL}data/`

async function readJson(path, signal) {
  const response = await fetch(`${DATA_BASE}${path}`, { signal })
  if (!response.ok) throw new Error(`Course data could not be loaded (${response.status}).`)
  return response.json()
}

export async function loadGuide(signal) {
  const manifest = await readJson('integration.json', signal)
  const entry = manifest.files?.history
  if (
    manifest.schema_version !== 1 || manifest.dataset !== 'professor_guide' ||
    manifest.data_kind !== 'live' || entry?.status !== 'available' ||
    !/^objects\/[a-f0-9]{64}\.json$/.test(entry.path)
  ) {
    throw new Error('The published data manifest is unavailable or unsupported.')
  }
  const history = await readJson(entry.path, signal)
  if (history.schema_version !== 2 || history.dataset !== 'teaching_history' ||
      history.data_kind !== 'live' || !Array.isArray(history.coverage?.terms)) {
    throw new Error('The teaching-history archive is unavailable or unsupported.')
  }
  return { manifest, history }
}
