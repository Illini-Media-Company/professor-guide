export const seasonOrder = { winter: 0, spring: 1, summer: 2, fall: 3 }
export const termOrder = (id) => Number(id.split('-')[0]) * 4 + (seasonOrder[id.split('-')[1]] ?? 0)
export const termLabel = (id) => {
  const [year, season] = id.split('-')
  return `${season[0].toUpperCase()}${season.slice(1)} ${year}`
}
export const shortTerm = (id) => `${({ winter: 'W', spring: 'Sp', summer: 'Su', fall: 'F' })[id.split('-')[1]]} ${id.slice(2, 4)}`
export const normalize = (text = '') => text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
export const number = (value) => value.toLocaleString('en-US')
export const dateLabel = (value) => value ? new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }) : 'Pending'
export const resultId = (person) => person.professor_id || person.entry_id
export function courseSource(course, term = '') {
  if (!course?.source_url) return null
  return term ? course.source_url.replace(/\/schedule\/\d{4}\/(winter|spring|summer|fall)\//, `/schedule/${term.replace('-', '/')}/`) : course.source_url
}

export function summarizeGrades(records) {
  const unique = [...new Map(records.map((row) => [row.id, row])).values()]
  if (!unique.length) return { gpa: null, students: null, records: 0 }
  const grains = new Map()
  for (const row of unique) {
    if (!grains.has(row.term_id)) grains.set(row.term_id, new Set())
    grains.get(row.term_id).add(row.grain)
  }
  if ([...grains.values()].some((group) => group.size > 1)) return { gpa: null, students: null, records: unique.length }
  const incomplete = unique.some((row) => row.student_count == null || (row.student_count > 0 && row.gpa == null))
  const students = unique.some((row) => row.student_count == null) ? null : unique.reduce((sum, row) => sum + row.student_count, 0)
  const numerator = unique.reduce((sum, row) => sum + (row.gpa ?? 0) * (row.student_count ?? 0), 0)
  return { gpa: !incomplete && students > 0 ? numerator / students : null, students, records: unique.length }
}

export function semesterHistory(records) {
  const groups = new Map()
  for (const row of records) groups.set(row.term_id, [...(groups.get(row.term_id) || []), row])
  return [...groups].map(([term, rows]) => ({ term, ...summarizeGrades(rows) })).sort((a, b) => termOrder(a.term) - termOrder(b.term))
}

export function createModel(index) {
  const courses = new Map(index.courses.map((course) => [course.course_code, course]))
  const grades = new Map()
  for (const row of index.grade_records) {
    const key = `${row.professor_id}|${row.course_code}`
    if (!grades.has(key)) grades.set(key, [])
    grades.get(key).push(row)
  }
  const entries = [...index.professors, ...(index.schedule_names || []).map((entry) => ({ ...entry,
    entry_type: 'schedule_name', professor_id: null, faculty_links: [], rmp: null,
  }))]
  const people = entries.map((person) => ({ ...person,
    searchText: normalize([person.display_name, ...person.courses.flatMap((c) => [c.course_code, courses.get(c.course_code)?.title || ''])].join(' ')),
  }))
  const peopleByCourse = new Map()
  for (const person of people) for (const course of person.courses) {
    if (!peopleByCourse.has(course.course_code)) peopleByCourse.set(course.course_code, [])
    peopleByCourse.get(course.course_code).push(person)
  }
  return { people, peopleById: new Map(people.map((p) => [resultId(p), p])), courses,
    subjects: [...new Set(index.courses.map((c) => c.course_code.split(' ')[0]))].sort(),
    terms: [...index.terms].sort((a, b) => termOrder(b.id) - termOrder(a.id)),
    gradesFor: (personId, code, term = '') => (personId == null ? [] : grades.get(`${personId}|${code}`) || []).filter((row) => !term || row.term_id === term),
    peopleFor: (code, term = '') => [...(peopleByCourse.get(code) || [])].filter((p) => !term || p.courses.some((c) => c.course_code === code && c.term_ids.includes(term))),
  }
}

export const isProfessorBrowse = (state) => state.view === 'professors' && !state.q.trim()

export function hasGpaFor(model, person, subject = '', term = '') {
  if (!person.professor_id) return false
  return person.courses.some((course) => (!subject || course.course_code.split(' ')[0] === subject) &&
    (!term || course.term_ids.includes(term)) && summarizeGrades(model.gradesFor(person.professor_id, course.course_code, term)).gpa != null)
}

export function searchResults(model, state) {
  const needle = normalize(state.q).trim()
  const matches = (text) => needle.split(/\s+/).every((part) => text.includes(part)) || text.replace(/\s+/g, '').includes(needle.replace(/\s+/g, ''))
  if (state.view === 'courses') {
    return [...model.courses.values()].filter((c) => (!state.subject || c.course_code.split(' ')[0] === state.subject) &&
      (!state.term || (c.term_ids ? c.term_ids.includes(state.term) : model.peopleFor(c.course_code, state.term).length > 0)) && matches(normalize(`${c.course_code} ${c.title || ''}`)))
      .sort((a, b) => a.course_code.localeCompare(b.course_code, 'en', { numeric: true }))
  }
  const ratedFirst = isProfessorBrowse(state)
  const filtered = model.people.filter((p) => matches(p.searchText) && (!state.subject && !state.term || p.courses.some((c) =>
    (!state.subject || c.course_code.split(' ')[0] === state.subject) && (!state.term || c.term_ids.includes(state.term)))))
  return filtered.sort((a, b) => {
    if (ratedFirst) {
      const group = Number(b.rmp?.overall_quality != null) - Number(a.rmp?.overall_quality != null)
      if (group) return group
    }
    if (state.sort === 'rating') {
      const diff = (b.rmp?.overall_quality ?? -1) - (a.rmp?.overall_quality ?? -1)
      if (diff) return diff
    }
    const last = (name) => name.split(' ').slice(-1)[0]
    return last(a.display_name).localeCompare(last(b.display_name)) || a.display_name.localeCompare(b.display_name)
  })
}

export function readState() {
  const params = new URLSearchParams(window.location.hash.slice(1))
  return { view: params.get('view') === 'courses' ? 'courses' : 'professors', q: params.get('q') || '',
    subject: params.get('subject') || '', term: params.get('term') || '', sort: params.get('sort') === 'rating' ? 'rating' : 'name',
    page: Math.max(1, Number(params.get('page')) || 1), person: params.get('person') || '', course: params.get('course') || '' }
}

export function stateUrl(state, fullPage = false) {
  const url = new URL(window.location.href)
  if (fullPage) url.searchParams.delete('embed')
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(state)) if (value && !(key === 'page' && value === 1)) params.set(key, String(value))
  url.hash = params.toString()
  return url
}
