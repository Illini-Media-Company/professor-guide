import { useEffect, useState } from 'react'

export default function IntegrationStatus() {
  const [manifest, setManifest] = useState(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${import.meta.env.BASE_URL}data/integration.json`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('Unavailable')
        return response.json()
      })
      .then(setManifest)
      .catch((failure) => { if (failure.name !== 'AbortError') setError(true) })
    return () => controller.abort()
  }, [])
  return (
    <section aria-labelledby="integration-title" className="mt-6 rounded border border-slate-200 p-4">
      <h2 id="integration-title" className="text-xl font-semibold">Integration preview</h2>
      {!manifest && <p role="status">{error ? 'Integration data is currently unavailable.' : 'Loading schedule coverage…'}</p>}
      {manifest && <>
        <p className="mt-2">{manifest.current_term.label}: {manifest.coverage.section_count.toLocaleString()} registration sections collected.</p>
        <ul className="mt-2 list-inside list-disc text-sm">
          <li>Course Explorer: available; source identities remain unresolved</li>
          <li>Grade data: {manifest.files.gpa.status === 'available' ? 'available' : 'awaiting grade-processing teammate'}</li>
          <li>Professor data: {manifest.files.professors.status === 'available' ? 'available' : 'awaiting matching teammate'}</li>
        </ul>
      </>}
    </section>
  )
}
