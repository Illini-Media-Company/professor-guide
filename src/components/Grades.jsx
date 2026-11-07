import { dateLabel, number, semesterHistory, shortTerm, summarizeGrades, termLabel } from '../guide.js'

export function Pending() {
  return <span className="pending">Pending</span>
}

export function Ratings({ rmp }) {
  const items = [
    ['Overall rating', rmp?.overall_quality, (v) => v.toFixed(1), '/ 5'],
    ['Difficulty', rmp?.difficulty, (v) => v.toFixed(1), '/ 5'],
    ['Would take again', rmp?.would_take_again_percent, (v) => `${Math.round(v)}%`, ''],
    ['Ratings', rmp?.num_ratings, number, ''],
  ]
  return <section className="ratings-section" aria-labelledby="ratings-title">
    <div className="section-heading"><h3 id="ratings-title">Student ratings</h3><span className="eyebrow muted">All courses</span></div>
    <dl className="ratings-grid">{items.map(([label, value, format, suffix]) => <div key={label}>
      <dt>{label}</dt><dd>{value == null ? <Pending /> : <>{format(value)} <small>{suffix}</small></>}</dd>
    </div>)}</dl>
    <p className="fine-print">{rmp?.source_url ? <><a href={rmp.source_url} target="_blank" rel="noopener noreferrer">Rate My Professors ↗</a> · Checked {dateLabel(rmp.collected_at)}.</> : 'Verified RMP data is pending.'}</p>
  </section>
}

export function GradeHistory({ records, code, term }) {
  const summary = summarizeGrades(records)
  const semesters = semesterHistory(records)
  const chart = semesters.slice(-6)
  return <section className="grade-section" aria-label={`Grades for ${code}`}>
    <div className="grade-summary">
      <div><p className="metric-label">GPA in {code}</p><p className="gpa-number">{summary.gpa == null ? <Pending /> : <>{summary.gpa.toFixed(2)}<small> / 4.00</small></>}</p></div>
      <div className="enrollment-summary"><strong>{summary.students == null ? <Pending /> : number(summary.students)}</strong><span>graded enrollments</span><span>{term ? termLabel(term) : 'All available semesters'}</span></div>
    </div>
    {semesters.length ? <>
      <div className="section-heading chart-heading"><h4>GPA by semester</h4><span className="fine-print">{semesters.length > 6 ? 'Latest 6 semesters' : ''}</span></div>
      <div className="gpa-chart" role="img" aria-label={`${code} GPA by semester. ${chart.map((s) => `${termLabel(s.term)}: ${s.gpa == null ? 'pending' : s.gpa.toFixed(2)}`).join('; ')}`}>
        <div className="chart-axis" aria-hidden="true"><span>4.0</span><span>2.0</span><span>0</span></div>
        <div className="chart-columns" style={{ gridTemplateColumns: `repeat(${chart.length}, minmax(0, 1fr))` }}>
          {chart.map((row) => <div className="chart-column" key={row.term} aria-hidden="true">
            <div className="bar-track"><div className="bar" style={{ height: `${(row.gpa ?? 0) / 4 * 100}%` }}><span className="bar-value">{row.gpa == null ? '—' : row.gpa.toFixed(2)}</span></div></div>
            <span className="bar-label">{shortTerm(row.term)}</span>
          </div>)}
        </div>
      </div>
      <details className="semester-details"><summary>View semester data <span aria-hidden="true">＋</span></summary>
        <table className="history-table"><caption className="sr-only">Semester GPA and graded enrollments for {code}</caption>
          <thead><tr><th scope="col">Semester</th><th scope="col">GPA</th><th scope="col">Enrollments</th></tr></thead>
          <tbody>{[...semesters].reverse().map((row) => <tr key={row.term}><th scope="row">{termLabel(row.term)}</th><td>{row.gpa == null ? 'Pending' : row.gpa.toFixed(2)}</td><td>{row.students == null ? 'Pending' : number(row.students)}</td></tr>)}</tbody>
        </table>
      </details>
    </> : null}
  </section>
}
