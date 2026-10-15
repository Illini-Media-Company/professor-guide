// BASE_URL includes the trailing slash and follows Vite's GitHub Pages base.
export const DATA_URL = `${import.meta.env.BASE_URL}data/course-explorer.json`

export async function loadCourseExplorer(signal) {
  const response = await fetch(DATA_URL, { signal })
  if (!response.ok) throw new Error(`Course data could not be loaded (${response.status}).`)
  const data = await response.json()
  if (
    data.schema_version !== 1 || data.dataset !== 'course_explorer' ||
    !['live', 'development_fixture'].includes(data.data_kind) ||
    !Array.isArray(data.courses) || !Array.isArray(data.sections) || !data.term
  ) {
    throw new Error('This data version is not supported by the starter.')
  }
  return data
}
