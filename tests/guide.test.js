import test from 'node:test'
import assert from 'node:assert/strict'
import { createModel, hasGpaFor, searchResults, semesterHistory, summarizeGrades } from '../src/guide.js'

const grade = (id, gpa, student_count, course_code = 'CS 101', term_id = '2025-fall') => ({ id, gpa, student_count, course_code, term_id, professor_id: 'a' })
const index = {
  professors: [
    { professor_id: 'a', display_name: 'Alexandra Café', rmp: { overall_quality: 0 }, courses: [{ course_code: 'CS 101', term_ids: ['2025-fall'] }] },
    { professor_id: 'b', display_name: 'No Rating', rmp: null, courses: [] },
    { professor_id: 'c', display_name: 'Higher Rating', rmp: { overall_quality: 4.5 }, courses: [{ course_code: 'CS 101', term_ids: ['2025-spring'] }] },
  ],
  courses: [{ course_code: 'CS 101', title: 'Introduction to computing' }],
  terms: [{ id: '2025-fall' }, { id: '2025-spring' }],
  grade_records: [grade('one', 0, 2), grade('two', 4, 6), grade('other-course', 1, 1, 'CS 202')],
}
const state = { view: 'professors', q: '', subject: '', term: '', sort: 'name' }

test('GPA is enrollment weighted; zero is a grade, and missing values stay unavailable', () => {
  assert.equal(summarizeGrades([grade('one', 0, 2), grade('two', 4, 6)]).gpa, 3)
  assert.equal(summarizeGrades([grade('one', 0, 2)]).gpa, 0)
  assert.deepEqual(summarizeGrades([]), { gpa: null, students: null, records: 0 })
  assert.equal(summarizeGrades([grade('one', 4, null)]).gpa, null)
  assert.equal(summarizeGrades([grade('one', null, 0)]).gpa, null)
})

test('Repeated references count once; distinct source rows remain separate', () => {
  const row = grade('one', 3, 10)
  assert.equal(summarizeGrades([row, row]).students, 10)
  assert.equal(summarizeGrades([row, { ...row, id: 'two' }]).students, 20)
})

test('Overlapping grains in one course/semester are not combined into a misleading average', () => {
  assert.equal(summarizeGrades([
    { ...grade('section', 3, 10), grain: 'section' },
    { ...grade('aggregate', 4, 100), grain: 'instructor_course_term' },
  ]).gpa, null)
})

test('Grades are isolated by professor, course, and selected semester', () => {
  const model = createModel(index)
  assert.equal(summarizeGrades(model.gradesFor('a', 'CS 101')).gpa, 3)
  assert.equal(model.gradesFor('b', 'CS 101').length, 0)
  assert.equal(model.gradesFor('a', 'CS 101', '2025-spring').length, 0)
})

test('GPA indicators require usable verified grades in the selected subject and semester', () => {
  const model = createModel(index)
  const person = model.peopleById.get('a')
  assert.equal(hasGpaFor(model, person), true)
  assert.equal(hasGpaFor(model, person, 'CS', '2025-fall'), true)
  assert.equal(hasGpaFor(model, person, 'MATH'), false)
  assert.equal(hasGpaFor(model, person, '', '2025-spring'), false)
  assert.equal(hasGpaFor(model, model.peopleById.get('c')), false)
  assert.equal(hasGpaFor(model, { ...person, professor_id: null }), false)
  const zeroOnly = createModel({ ...index, grade_records: [grade('zero', 0, 1)] })
  assert.equal(hasGpaFor(zeroOnly, person), true)
  const missing = createModel({ ...index, grade_records: [grade('missing', null, 1)] })
  assert.equal(hasGpaFor(missing, person), false)
})

test('Search handles accents and course codes without spaces and retains unrated instructors', () => {
  const model = createModel(index)
  assert.equal(searchResults(model, { ...state, q: 'Cafe' })[0].professor_id, 'a')
  assert.equal(searchResults(model, { ...state, q: 'cs101' }).length, 2)
  assert.equal(searchResults(model, { ...state, q: 'No Rating' })[0].professor_id, 'b')
  assert.deepEqual(searchResults(model, { ...state, sort: 'rating' }).map((p) => p.professor_id), ['c', 'a', 'b'])
})

test('Browsing puts rated instructors first, then pending entries, alphabetically within each group', () => {
  const data = structuredClone(index)
  data.professors.push({ professor_id: 'd', display_name: 'Avery Adams', rmp: { overall_quality: null, num_ratings: 0 }, courses: [{ course_code: 'CS 101', term_ids: ['2025-fall'] }] })
  const model = createModel(data)
  assert.deepEqual(searchResults(model, state).map((p) => p.professor_id), ['a', 'c', 'd', 'b'])
  assert.deepEqual(searchResults(model, { ...state, q: '   ' }).map((p) => p.professor_id), ['a', 'c', 'd', 'b'])
  assert.equal(searchResults(model, { ...state, q: 'Avery' })[0].professor_id, 'd')
  assert.deepEqual(searchResults(model, { ...state, subject: 'CS' }).map((p) => p.professor_id), ['a', 'c', 'd'])
  assert.deepEqual(searchResults(model, { ...state, term: '2025-fall' }).map((p) => p.professor_id), ['a', 'd'])
  assert.deepEqual(searchResults(model, { ...state, subject: 'CS', term: '2025-fall' }).map((p) => p.professor_id), ['a', 'd'])
  assert.deepEqual(searchResults(model, { ...state, q: 'CS101', subject: 'CS', term: '2025-fall' }).map((p) => p.professor_id), ['d', 'a'])
})

test('Subject and semester filters apply to the same verified assignment', () => {
  const model = createModel(index)
  assert.deepEqual(searchResults(model, { ...state, subject: 'CS', term: '2025-fall' }).map((p) => p.professor_id), ['a'])
  assert.equal(searchResults(model, { ...state, subject: 'MATH' }).length, 0)
  assert.equal(searchResults(model, { ...state, view: 'courses', q: 'CS101' }).length, 1)
})

test('Semester history follows the academic calendar rather than alphabetical season names', () => {
  const rows = ['fall', 'winter', 'summer', 'spring'].map((s) => grade(s, 3, 1, 'CS 101', `2025-${s}`))
  assert.deepEqual(semesterHistory(rows).map((r) => r.term), ['2025-winter', '2025-spring', '2025-summer', '2025-fall'])
})

test('The catalog includes ungraded courses, courses with unnamed teachers, and source-name entries', () => {
  const complete = structuredClone(index)
  complete.courses.push({ course_code: 'ECE 374', title: 'Algorithms', term_ids: ['2026-fall'] })
  complete.courses.push({ course_code: 'ECE 599', title: 'Independent study', term_ids: ['2026-fall'] })
  complete.schedule_names = [{ entry_id: 'schedule_fox', subject: 'ECE', display_name: 'Fox, E', courses: [{ course_code: 'ECE 374', term_ids: ['2026-fall'] }] }]
  const model = createModel(complete)
  assert.equal(searchResults(model, { ...state, view: 'courses', q: 'ECE374', term: '2026-fall' }).length, 1)
  assert.equal(searchResults(model, { ...state, view: 'courses', q: 'ECE599', term: '2026-fall' }).length, 1)
  const sourceName = searchResults(model, { ...state, q: 'Fox', subject: 'ECE', term: '2026-fall' })[0]
  assert.equal(sourceName.entry_type, 'schedule_name')
  assert.equal(sourceName.professor_id, null)
  assert.equal(sourceName.rmp, null)
  assert.equal(model.gradesFor(sourceName.professor_id, 'ECE 374').length, 0)
})

const sourceEntry = (entry_id, display_name, subject, term = '2026-fall') => ({
  entry_id, display_name, subject, courses: [{ course_code: `${subject} 101`, term_ids: [term] }],
})

test('Initial and surname variants produce one profile across departments without changing grade attribution', () => {
  const data = structuredClone(index)
  data.schedule_names = [sourceEntry('cs', 'Cafe, A', 'CS'), sourceEntry('math', 'Café, A', 'MATH'),
    sourceEntry('ece', 'Café, A', 'ECE', '2025-fall')]
  const before = structuredClone(data)
  const model = createModel(data)
  const person = model.peopleById.get('a')
  assert.equal(model.people.length, 3)
  assert.equal(model.peopleById.get('math'), person)
  assert.equal(model.peopleById.get('ece'), person)
  assert.deepEqual(person.courses.find((c) => c.course_code === 'CS 101').term_ids, ['2025-fall', '2026-fall'])
  for (const subject of ['CS', 'MATH', 'ECE']) {
    assert.equal(searchResults(model, { ...state, q: 'Cafe, A', subject }).length, 1)
  }
  assert.equal(searchResults(model, { ...state, subject: 'MATH', term: '2025-fall' }).length, 0)
  assert.equal(model.peopleFor('CS 101', '2026-fall').length, 1)
  assert.equal(model.gradesFor('a', 'MATH 101').length, 0)
  assert.equal(model.gradesFor('a', 'CS 101', '2026-fall').length, 0)
  assert.deepEqual(data, before)
})

test('Long surname typos and truncations group with a unique compatible professor', () => {
  const data = { ...index, professors: [{ professor_id: 'p', display_name: 'Peter Abbamonte', courses: [] }],
    schedule_names: [sourceEntry('one', 'Abbamont, P', 'PHYS'), sourceEntry('two', 'Abbamonte, P', 'ECE'),
      sourceEntry('three', 'Abbamonte, Q', 'CS')] }
  const model = createModel(data)
  assert.equal(model.peopleById.get('one').professor_id, 'p')
  assert.equal(model.peopleById.get('two').professor_id, 'p')
  assert.equal(model.peopleById.get('three').professor_id, null)
})

test('Conflicting full names, middle initials, and competing identities remain separate', () => {
  const data = { ...index, professors: [
    { professor_id: 'jane', display_name: 'Jane X Smith', courses: [] },
    { professor_id: 'john', display_name: 'John Y Smith', courses: [] },
  ], schedule_names: [sourceEntry('ambiguous', 'Smith, J', 'CS'),
    sourceEntry('conflict', 'Smith, Jane Z', 'MATH'), sourceEntry('specific', 'Smith, Jane X', 'ECE')] }
  const model = createModel(data)
  assert.equal(model.peopleById.get('ambiguous').professor_id, null)
  assert.equal(model.peopleById.get('conflict').professor_id, null)
  assert.equal(model.peopleById.get('specific').professor_id, 'jane')
  assert.notEqual(model.peopleById.get('ambiguous'), model.peopleById.get('conflict'))
})

test('Unidentified names group across subjects with original links and pending metrics', () => {
  const data = { ...index, schedule_names: [sourceEntry('one', 'Longsurname, L', 'CS'),
    sourceEntry('two', 'Longsurname, L', 'ECE'), sourceEntry('typo', 'Longsurnam, L', 'MATH')] }
  const model = createModel(data)
  const person = model.peopleById.get('one')
  assert.equal(model.people.length, 4)
  assert.equal(model.peopleById.get('two'), person)
  assert.equal(model.peopleById.get('typo'), person)
  assert.deepEqual(person.subjects, ['CS', 'ECE', 'MATH'])
  assert.equal(person.rmp, null)
  assert.equal(person.professor_id, null)
  assert.equal(model.peopleFor('ECE 101').length, 1)
})

test('A shared initial cannot bridge incompatible full names or a chain of surname typos', () => {
  const data = { ...index, professors: [], schedule_names: [sourceEntry('a', 'Longsurname, Alex', 'CS'),
    sourceEntry('b', 'Longsurname, A', 'ECE'), sourceEntry('c', 'Longsurname, Amanda', 'MATH'),
    sourceEntry('d', 'Longsurnamx, A', 'CS'), sourceEntry('e', 'Longsurnaxx, A', 'ECE')] }
  const model = createModel(data)
  assert.notEqual(model.peopleById.get('a'), model.peopleById.get('c'))
  assert.notEqual(model.peopleById.get('d'), model.peopleById.get('e'))
})

test('Names without given initials only group identical labels', () => {
  const model = createModel({ ...index, schedule_names: [sourceEntry('one', 'Longsurname', 'CS'),
    sourceEntry('two', 'Longsurname', 'ECE'), sourceEntry('other', 'Othersurname', 'MATH')] })
  assert.equal(model.peopleById.get('one'), model.peopleById.get('two'))
  assert.notEqual(model.peopleById.get('one'), model.peopleById.get('other'))
  assert.equal(model.peopleById.get('other').display_name, 'Othersurname')
})
