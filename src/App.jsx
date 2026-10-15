import { useEffect, useState } from 'react'
import { DATA_BASE, loadGuide } from './data.js'

const number = (value) => value.toLocaleString()

export default function App() {
  const [guide, setGuide] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    loadGuide(controller.signal).then(setGuide).catch((failure) => {
      if (failure.name !== 'AbortError') setError(failure.message)
    })
    return () => controller.abort()
  }, [])

  return (
    <main className="mx-auto max-w-4xl px-5 py-10 text-slate-900">
      <header className="border-b border-slate-200 pb-6">
        <p className="text-sm font-semibold uppercase tracking-widest text-orange-800">The Daily Illini</p>
        <h1 className="mt-2 text-4xl font-bold">Professor Guide</h1>
        <p className="mt-3 text-slate-600">Official UIUC course and teaching-assignment data.</p>
      </header>

      {error && <p role="alert" className="mt-6 rounded border border-red-300 bg-red-50 p-4">{error}</p>}
      {!guide && !error && <p role="status" className="mt-6">Loading course coverage…</p>}
      {guide && <>
        <section aria-labelledby="current-title" className="mt-6 rounded border border-slate-200 p-4">
          <h2 id="current-title" className="text-xl font-semibold">{guide.manifest.current_term.label}</h2>
          <p className="mt-2">{number(guide.manifest.coverage.section_count)} registration sections collected.</p>
          <p className="mt-2 text-sm text-slate-600">Saved source data; assignments can change. Original instructor names are preserved and professor identities await verification.</p>
          <a className="mt-3 inline-block text-blue-800 underline" href={`${DATA_BASE}${guide.manifest.files.schedule.path}`} download>Download current schedule JSON</a>
        </section>

        <section aria-labelledby="history-title" className="mt-8">
          <h2 id="history-title" className="text-xl font-semibold">Teaching history</h2>
          <p className="mt-2">{guide.history.start_year} through {guide.manifest.current_term.label}: {number(guide.history.coverage.totals.collected_terms)} terms, {number(guide.history.coverage.totals.course_count)} course listings, and {number(guide.history.coverage.totals.section_count)} registration sections.</p>
          <p className="mt-2 text-sm text-slate-600">Each collected term covers every department listed by Course Explorer. Cross-listed registrations remain separate; these totals are not counts of unique professors or teaching groups.</p>
          <ul className="mt-4 space-y-3">
            {[...guide.history.coverage.terms].reverse().map((term) => <li key={term.term_id} className="rounded border border-slate-200 p-4">
              <h3 className="font-semibold">{term.term?.label || term.term_id}</h3>
              {term.status === 'collected' ? <>
                <p className="mt-1 text-sm">{number(term.department_count)} departments · {number(term.course_count)} listings · {number(term.section_count)} sections</p>
                <details className="mt-2 text-sm">
                  <summary className="cursor-pointer font-medium">Assignment coverage and source date</summary>
                  <p className="mt-2">{number(term.missing_instructor_meetings)} meetings without listed instructors; {number(term.multiple_instructor_meetings)} meetings with multiple instructors.</p>
                  <p className="mt-1">Latest schedule fetch: <time dateTime={term.snapshot.collected_at}>{new Date(term.snapshot.collected_at).toLocaleString()}</time>.</p>
                </details>
                <a className="mt-2 inline-block text-sm text-blue-800 underline" href={`${DATA_BASE}${term.snapshot.path}`} download>Download {term.term.label} JSON</a>
              </> : <p className="mt-1 text-sm">Unavailable in the official term index ({term.reason}).</p>}
            </li>)}
          </ul>
        </section>
        <p className="mt-6 text-sm"><a className="text-blue-800 underline" href="https://courses.illinois.edu/" target="_blank" rel="noopener noreferrer">Source: UIUC Course Explorer</a></p>
      </>}
    </main>
  )
}
