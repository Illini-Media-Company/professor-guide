import { useEffect, useState } from 'react'
import { loadGuide } from './data.js'
import Guide, { DataNotes } from './Guide.jsx'

export default function App() {
  const [guide, setGuide] = useState(null)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    setGuide(null)
    loadGuide(controller.signal).then((data) => {
      if (!controller.signal.aborted) setGuide(data)
    }).catch((failure) => {
      if (failure.name !== 'AbortError') setError(failure.message)
    })
    return () => controller.abort()
  }, [attempt])
  return <main className="guide-shell">
    {!guide?.index && <header className="guide-header"><h1>Professor Guide</h1></header>}
    {error && <section role="alert" className="load-message"><h2>We couldn’t load the guide.</h2><p>{error}</p><button className="secondary-button" onClick={() => setAttempt((n) => n + 1)}>Try again</button></section>}
    {!guide && !error && <div className="load-message" role="status"><span className="loading-mark" aria-hidden="true" />Loading the Professor Guide…</div>}
    {guide?.index && <Guide guide={guide} />}
    {guide && !guide.index && <><section className="load-message"><h2>Search data is pending.</h2><p>The searchable guide is being prepared. The available source downloads are below.</p></section><DataNotes guide={guide} /></>}
  </main>
}
