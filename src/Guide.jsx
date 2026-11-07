import { useEffect, useMemo, useRef, useState } from 'react'
import { DATA_BASE } from './data.js'
import { courseSource, createModel, dateLabel, hasGpaFor, isProfessorBrowse, number, readState, resultId, searchResults, stateUrl, summarizeGrades, termLabel, termOrder } from './guide.js'
import { GradeHistory, Pending, Ratings } from './components/Grades.jsx'

const PAGE_SIZE = 5
const Arrow = () => <span aria-hidden="true">↗</span>
const GpaIcon = () => <span className="gpa-indicator" title="GPA data available"><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" role="img" aria-label="GPA data available"><path d="M1 1h1v12h13v1H1zM4 8h2v3H4zm4-4h2v7H8zm4 2h2v5h-2z" /></svg></span>

export function DataNotes({ guide }) {
  const { manifest, index } = guide
  const downloads = [['schedule', 'Current schedule'], ['history', 'Teaching archive index'], ['gpa', 'Grade records'], ['professors', 'Instructor data']]
  return <details className="data-notes"><summary>About the data <span aria-hidden="true">＋</span></summary>
    <div className="notes-content">
      <p>Before a text search, instructors with RMP ratings appear first, followed by listings with pending ratings. Each group is alphabetical by last name, including when subject or semester filters are applied. The guide includes all collected UIUC courses, identified instructors, and names recorded in schedules. Schedule-name entries keep their original spelling and initials; they are not verified person profiles. GPA is course-specific; Rate My Professors ratings cover an instructor across courses. <strong>Pending</strong> means verified data is not available in this edition.</p>
      <p>Teaching records include instructors and other listed staff, not necessarily current assignments. GPA is weighted by graded enrollments; counts can include repeat students. Cross-listed courses remain separate.</p>
      <div className="notes-links"><a href="https://courses.illinois.edu/" target="_blank" rel="noopener noreferrer">UIUC Course Explorer <Arrow /></a>
        {index?.gpa_sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer">Grade data source <Arrow /></a>)}</div>
      <p className="fine-print">{index && <>{number(index.coverage.professors)} identified instructors · {number(index.coverage.courses)} courses. </>}Prepared data: {dateLabel(manifest.collected_at)}. Individual ratings retain their own source dates.</p>
      <div className="download-links">{downloads.map(([key, label]) => manifest.files[key]?.status === 'available' && <a key={key} href={`${DATA_BASE}${manifest.files[key].path}`} download>{label} JSON ↓</a>)}</div>
    </div>
  </details>
}

function Profile({ person, model, courseCode, term, selectCourse }) {
  const unresolved = person.entry_type === 'schedule_name'
  const eligible = person.courses.filter((c) => !term || c.term_ids.includes(term))
  const courses = eligible.length ? eligible : person.courses
  const sorted = [...courses].sort((a, b) => Math.max(...b.term_ids.map(termOrder)) - Math.max(...a.term_ids.map(termOrder)) || a.course_code.localeCompare(b.course_code))
  const code = courses.some((c) => c.course_code === courseCode) ? courseCode : sorted[0]?.course_code
  const teachingTerms = [...(courses.find((c) => c.course_code === code)?.term_ids || [])].sort((a, b) => termOrder(b) - termOrder(a))
  const source = courseSource(model.courses.get(code), term || teachingTerms[0])
  const universityLink = person.faculty_links.find((l) => /\/profile\/|\/people\//.test(l.url)) || person.faculty_links[0]
  return <>
    <div className="profile-heading">{unresolved && <p className="eyebrow muted">Schedule name · identity pending</p>}<h2 tabIndex={-1} id="detail-heading">{person.display_name}</h2>
      <div className="profile-meta"><span>{person.courses.length ? `${number(person.courses.length)} recorded ${person.courses.length === 1 ? 'course' : 'courses'}` : 'Course links pending'}</span>
        {universityLink && <a href={universityLink.url} target="_blank" rel="noopener noreferrer">University listing <Arrow /></a>}</div>
      {unresolved && <p className="identity-note">This is the name as recorded in {person.subject} schedules. The same abbreviation may refer to different people. Full identity verification is pending.</p>}
    </div>
    <Ratings rmp={person.rmp} />
    <section className="teaching-section" aria-labelledby="teaching-title">
      <div className="section-heading"><h3 id="teaching-title">Course grades</h3></div>
      {code ? <><label className="field course-picker"><span>Course</span><select value={code} onChange={(e) => selectCourse(e.target.value)}>
        {sorted.map((c) => <option key={c.course_code} value={c.course_code}>{c.course_code} · {model.courses.get(c.course_code)?.title || 'Course title unavailable'}</option>)}
      </select></label>
        <details className="teaching-terms"><summary>Teaching history</summary><p>{teachingTerms.map(termLabel).join(' · ')}</p></details>
        <GradeHistory key={`${person.professor_id}|${code}`} records={model.gradesFor(person.professor_id, code, term)} code={code} term={term} />
        {source && <a className="source-link" href={source} target="_blank" rel="noopener noreferrer">Course Explorer source <Arrow /></a>}
      </> : <p className="empty-grades">Verified course and GPA links for this instructor are pending.</p>}
    </section>
  </>
}

function Course({ course, model, term, selectPerson }) {
  const [visible, setVisible] = useState(12)
  const people = model.peopleFor(course.course_code, term).sort((a, b) => Number(a.entry_type === 'schedule_name') - Number(b.entry_type === 'schedule_name') || a.display_name.localeCompare(b.display_name))
  return <>
    <div className="profile-heading"><h2 tabIndex={-1} id="detail-heading">{course.course_code}</h2><p className="course-title">{course.title || 'Course title pending'}</p>
      {course.source_url && <a className="source-link" href={courseSource(course, term)} target="_blank" rel="noopener noreferrer">Course Explorer source <Arrow /></a>}</div>
    <section className="course-instructors"><div className="section-heading"><h3>Teaching staff</h3><span className="count-badge">{number(people.length)}</span></div>
      <p className="fine-print">{term ? termLabel(term) : 'All semesters'}</p>
      {!people.length && <p className="empty-grades">Instructor names are pending in the available schedule records for this course{term ? ' and semester' : ''}.</p>}
      <table className="course-people-table"><caption className="sr-only">Recorded teaching names for {course.course_code}</caption><thead><tr><th scope="col">Name</th><th scope="col">Course GPA</th><th scope="col">Enrollments</th></tr></thead>
        <tbody>{people.slice(0, visible).map((person) => { const summary = summarizeGrades(model.gradesFor(person.professor_id, course.course_code, term)); return <tr key={resultId(person)}>
          <td><button className="name-button" onClick={() => selectPerson(resultId(person), course.course_code)}>{person.display_name}<span aria-hidden="true"> →</span></button>{person.entry_type === 'schedule_name' && <span className="source-name-label">Identity pending</span>}</td>
          <td>{summary.gpa == null ? <Pending /> : summary.gpa.toFixed(2)}</td><td>{summary.students == null ? '—' : number(summary.students)}</td>
        </tr> })}</tbody>
      </table>
      {people.length > visible && <button className="secondary-button more-names" onClick={() => setVisible((n) => n + 12)}>Show more names ({number(people.length - visible)} remaining)</button>}
    </section>
  </>
}

export default function Guide({ guide }) {
  const model = useMemo(() => createModel(guide.index), [guide.index])
  const [state, setState] = useState(readState)
  const root = useRef(null)
  const focusDetails = useRef(false)
  useEffect(() => {
    const restore = () => setState(readState())
    window.addEventListener('popstate', restore)
    window.addEventListener('hashchange', restore)
    return () => { window.removeEventListener('popstate', restore); window.removeEventListener('hashchange', restore) }
  }, [])
  const update = (changes, push = false) => {
    const next = { ...state, ...changes }
    window.history[push ? 'pushState' : 'replaceState']({}, '', stateUrl(next))
    setState(next)
  }
  const filter = (changes) => update({ ...changes, page: 1, person: '', course: '' })
  const term = model.terms.some((t) => t.id === state.term) ? state.term : ''
  const subject = model.subjects.includes(state.subject) ? state.subject : ''
  const ratedFirst = isProfessorBrowse({ ...state, subject, term })
  const results = useMemo(() => searchResults(model, { ...state, subject, term }), [model, state, subject, term])
  const pages = Math.max(1, Math.ceil(results.length / PAGE_SIZE))
  const page = Math.min(pages, Math.floor(state.page))
  const pageRows = results.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const person = state.person ? model.peopleById.get(state.person) : null
  const course = state.view === 'courses' && state.course ? model.courses.get(state.course) : null
  const hasSelection = Boolean(state.person || state.course && state.view === 'courses')
  useEffect(() => {
    if (focusDetails.current) {
      root.current?.querySelector('#detail-heading')?.focus({ preventScroll: true })
      if (window.matchMedia('(max-width: 899px)').matches) root.current?.querySelector('.detail-pane')?.scrollIntoView({ block: 'start' })
      focusDetails.current = false
    }
  }, [state.person, state.course])
  const select = (changes) => { focusDetails.current = true; update(changes, true) }
  const close = () => {
    const id = state.person || state.course
    update({ person: '', course: '' }, true)
    requestAnimationFrame(() => (document.getElementById(`result-${id}`) || document.getElementById('guide-search'))?.focus({ preventScroll: true }))
  }
  return <div ref={root} className={`guide-content${hasSelection ? ' has-selection' : ''}`}>
    <section className="search-toolbar" aria-labelledby="search-title">
      <div className="search-heading"><h1 id="search-title">Professor Guide</h1>
        <label className="view-picker"><span>Search for</span><select value={state.view} onChange={(e) => filter({ view: e.target.value })}><option value="professors">Professors</option><option value="courses">Courses</option></select></label>
      </div>
      <div className="search-fields"><label className="field search-field"><span>Search</span><div className="search-input-wrap">
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
        <input id="guide-search" type="search" value={state.q} onChange={(e) => filter({ q: e.target.value })} placeholder={state.view === 'professors' ? 'Name, course code or course title' : 'Course code or title'} />
      </div></label>
        <label className="field"><span>Subject</span><select value={subject} onChange={(e) => filter({ subject: e.target.value })}><option value="">All subjects</option>{model.subjects.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label className="field"><span>Semester</span><select value={term} onChange={(e) => filter({ term: e.target.value })}><option value="">All semesters</option>{model.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
      </div>
    </section>
    <div className="workspace">
      <section className="results-pane" aria-labelledby="results-title">
        <div className="results-heading"><div><h3 id="results-title">{state.view === 'professors' ? 'Professors' : 'Courses'}</h3><p role="status" aria-live="polite">{number(results.length)} {results.length === 1 ? 'result' : 'results'}{state.q ? ` for “${state.q}”` : ''}</p></div>
          {(state.q || subject || term) && <button className="text-button" onClick={() => filter({ q: '', subject: '', term: '' })}>Clear filters</button>}
        </div>
        <table className="results-table"><caption className="sr-only">{state.view === 'professors' ? 'Professor' : 'Course'} search results</caption>
          <thead><tr><th scope="col" aria-sort={state.sort === 'name' || state.view === 'courses' ? 'ascending' : 'none'}><button className="sort-button" onClick={() => filter({ sort: 'name' })}>{state.view === 'professors' ? 'Name' : 'Course'} <span aria-hidden="true">↓</span></button></th>
            <th scope="col" aria-sort={state.view === 'professors' && state.sort === 'rating' ? 'descending' : 'none'}>{state.view === 'professors' ? <button className="sort-button" onClick={() => filter({ sort: 'rating' })}>RMP <span aria-hidden="true">↓</span></button> : 'Names listed'}</th></tr></thead>
          <tbody>{pageRows.map((row) => { const id = row.professor_id || row.entry_id || row.course_code; const selected = person && resultId(person) === id || course?.course_code === id; return <tr className={selected ? 'selected' : ''} key={id}>
            <td><button id={`result-${id}`} className="result-link" aria-current={selected ? 'true' : undefined} onClick={() => select(state.view === 'professors' ? { person: id, course: '' } : { person: '', course: id })}>
              <strong>{state.view === 'professors' ? row.display_name : row.course_code}{state.view === 'professors' && hasGpaFor(model, row, subject, term) && <GpaIcon />}</strong>
              <span>{state.view === 'professors' ? (row.entry_type === 'schedule_name' ? `${row.subject} · Identity pending` : [...new Set(row.courses.map((c) => c.course_code.split(' ')[0]))].slice(0, 4).join(' · ') || 'Course links pending') : row.title || 'Course title pending'}</span>
            </button></td><td className="result-stat">{state.view === 'professors' ? <>{row.rmp?.overall_quality == null ? <Pending /> : <><strong>{row.rmp.overall_quality.toFixed(1)}<small> / 5</small></strong><span>{number(row.rmp.num_ratings)} ratings</span></>}</> : <strong>{number(model.peopleFor(row.course_code, term).length)}</strong>}</td>
          </tr> })}</tbody>
        </table>
        {!pageRows.length && <div className="no-results"><h4>No results found</h4><p>Try another name or course, or clear your filters.</p><button className="secondary-button" onClick={() => filter({ q: '', subject: '', term: '' })}>Clear filters</button></div>}
        <div className="pagination"><span>{results.length ? `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, results.length)} of ${number(results.length)}` : '0 results'}</span><div><button disabled={page <= 1} onClick={() => update({ page: page - 1, person: '', course: '' })} aria-label="Previous results page">Prev</button><span>{page} / {pages}</span><button disabled={page >= pages} onClick={() => update({ page: page + 1, person: '', course: '' })} aria-label="Next results page">Next</button></div></div>
        {ratedFirst && <p className="results-note">RMP-rated instructors first, then pending.</p>}
      </section>
      <section className={`detail-pane${hasSelection ? ' is-open' : ''}`} aria-label="Selected result details">
        {hasSelection ? <><div className="detail-actions"><button className="back-button" onClick={close}>← Back to results</button><a href={stateUrl(state, true).href} target="_blank" rel="noopener noreferrer">Open full page <Arrow /></a></div>
          {person ? <Profile person={person} model={model} courseCode={state.course} term={term} selectCourse={(code) => update({ course: code })} /> : course ? <Course key={`${course.course_code}|${term}`} course={course} model={model} term={term} selectPerson={(id, code) => select({ view: 'professors', person: id, course: code })} /> : <div role="alert" className="empty-detail"><h2>This result is unavailable</h2><p>Return to the results to choose another instructor or course.</p></div>}
        </> : <div className="empty-detail"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg><p>Select a professor or course to view details</p></div>}
      </section>
    </div>
    <DataNotes guide={guide} />
  </div>
}
