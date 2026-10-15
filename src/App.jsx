import { useEffect, useState } from 'react'
import { loadCourseExplorer } from './data.js'
import IntegrationStatus from './IntegrationStatus.jsx'

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    loadCourseExplorer(controller.signal)
      .then(setData)
      .catch((failure) => {
        if (failure.name !== 'AbortError') setError(failure.message)
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="mx-auto max-w-4xl px-5 py-10 text-slate-900">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-semibold uppercase tracking-widest text-orange-800">The Daily Illini</p>
        <h1 className="mt-2 text-4xl font-bold">Professor Guide</h1>
        <p className="mt-3 text-slate-600">A starting point for exploring UIUC courses and professors.</p>
      </header>

      <IntegrationStatus />
      <section className="mt-6" aria-labelledby="sample-title" aria-busy={!data && !error}>
        <h2 id="sample-title" className="text-xl font-semibold">Course data preview</h2>
        <p className="mt-2 text-sm text-slate-600">Development preview. Search, profiles, GPA, and rating summaries are being built.</p>
        {error && <p role="alert" className="mt-4 rounded border border-red-300 bg-red-50 p-4">{error}</p>}
        {!data && !error && <p role="status" className="mt-4">Loading saved course data…</p>}
        {data && (
          <>
            <p className="mt-4 rounded border border-slate-200 bg-slate-50 p-4 text-sm">
              <strong>{data.data_kind === 'live' ? 'Collected from Course Explorer' : 'Development fixture — synthetic data'}</strong>
              {' · '}{data.term.label}{' · '}{data.sections.length} registration sections
              <br />
              Source snapshot: <time dateTime={data.collected_at}>{new Date(data.collected_at).toLocaleString()}</time>.
              {' '}This is a saved snapshot. Professor identities are unresolved.
            </p>
            <ul className="mt-4 space-y-4">
              {data.courses.map((course) => {
                const sections = data.sections.filter((section) => section.listing_id === course.listing_id)
                const related = [...new Set(data.relationships
                  .filter((relationship) => relationship.from_listing_id === course.listing_id)
                  .map((relationship) => relationship.to_course_code))]
                return (
                  <li key={course.listing_id} className="rounded border border-slate-200 p-4">
                    <h3 className="font-semibold">{course.course_code} · {course.title}</h3>
                    <p className="mt-1 text-sm text-slate-600">
                      {sections.length} separate registration sections
                      {related.length > 0 && ` · Related listing: ${related.join(', ')}`}
                    </p>
                    <details className="mt-3 text-sm">
                      <summary className="cursor-pointer font-medium">Inspect sections and listed instructors</summary>
                      <ul className="mt-2 space-y-3">
                        {sections.map((section) => (
                          <li key={section.id}>
                            <strong>{section.section_label}</strong> · CRN {section.crn}
                            <ul className="ml-4 list-disc">
                              {section.meetings.map((meeting) => (
                                <li key={meeting.id}>
                                  {meeting.type.label} ({meeting.type.code})
                                  {' · '}{meeting.instructors.length
                                    ? meeting.instructors.map((person) => person.name_raw).join('; ')
                                    : 'No instructor listed'}
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                      </ul>
                    </details>
                    <a className="mt-3 inline-block text-sm text-blue-800 underline" href={course.source_url} target="_blank" rel="noreferrer">Course Explorer source XML</a>
                  </li>
                )
              })}
            </ul>
          </>
        )}
      </section>
    </main>
  )
}
