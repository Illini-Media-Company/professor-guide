// Visitor-facing name grouping. Source records and verified grade joins stay intact.
const words = (value) => value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
  .replace(/[^\p{L}\p{N}\s]/gu, '').trim().split(/\s+/).filter(Boolean)

function nameParts(name) {
  const comma = name.indexOf(',')
  if (comma >= 0) return { surnames: [words(name.slice(0, comma)).join('')], given: words(name.slice(comma + 1)) }
  const tokens = words(name)
  if (tokens.length < 2) return { surnames: [tokens.join('')], given: [] }
  return { surnames: tokens.slice(1).map((_, i) => tokens.slice(i + 1).join('')), given: tokens.slice(0, -1) }
}

function similarSurname(a, b) {
  if (a === b) return true
  if (Math.min(a.length, b.length) < 6) return false
  // Allow a long truncated surname or one inserted/deleted/substituted letter.
  if ((a.startsWith(b) || b.startsWith(a)) && Math.min(a.length, b.length) / Math.max(a.length, b.length) >= 0.8) return true
  if (Math.abs(a.length - b.length) > 1) return false
  let i = 0, j = 0, edits = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue }
    if (++edits > 1) return false
    if (a.length >= b.length) i++
    if (b.length >= a.length) j++
  }
  return edits + (a.length - i) + (b.length - j) <= 1
}

function compatible(a, b, fuzzy = false) {
  if (!a.given.length || !b.given.length) return false
  const first = (x, y) => x === y || x.length === 1 && x === y[0] || y.length === 1 && y === x[0]
  return a.given.every((token, i) => !b.given[i] || first(token, b.given[i])) &&
    a.surnames.some((x) => x && b.surnames.some((y) => fuzzy ? similarSurname(x, y) : x === y))
}

function combineCourses(entries) {
  const courses = new Map()
  for (const entry of entries) for (const course of entry.courses) {
    if (!courses.has(course.course_code)) courses.set(course.course_code, new Set())
    for (const term of course.term_ids) courses.get(course.course_code).add(term)
  }
  return [...courses].sort(([a], [b]) => a.localeCompare(b)).map(([course_code, terms]) => ({ course_code, term_ids: [...terms].sort() }))
}

export function groupPeople(index) {
  const known = index.professors.map((person) => ({ ...person, source_entries: [], alias_ids: [], names: [person.display_name] }))
  const buckets = new Map()
  const add = (entry) => {
    const initial = entry.parts.given[0]?.[0]
    if (!buckets.has(initial)) buckets.set(initial, [])
    buckets.get(initial).push(entry)
  }
  for (const person of known) add({ person, parts: nameParts(person.display_name) })
  // First collapse identical labels across departments, retaining every original ID.
  const labels = new Map()
  for (const entry of index.schedule_names || []) {
    const parts = nameParts(entry.display_name)
    const key = JSON.stringify(parts)
    if (!labels.has(key)) labels.set(key, { parts, entries: [] })
    labels.get(key).entries.push(entry)
  }
  const pending = []
  for (const label of labels.values()) {
    const candidates = buckets.get(label.parts.given[0]?.[0]) || []
    const exact = candidates.filter((candidate) => compatible(label.parts, candidate.parts))
    const matches = exact.length ? exact : candidates.filter((candidate) => compatible(label.parts, candidate.parts, true))
    if (matches.length === 1) matches[0].person.source_entries.push(...label.entries)
    else pending.push({ ...label, ambiguous: matches.length > 1 })
  }
  const unresolved = []
  const consumed = new Set()
  const pendingBuckets = new Map()
  for (const label of pending) {
    const initial = label.parts.given[0]?.[0]
    if (!pendingBuckets.has(initial)) pendingBuckets.set(initial, [])
    pendingBuckets.get(initial).push(label)
  }
  for (const label of pending) {
    if (consumed.has(label)) continue
    const neighbors = (pendingBuckets.get(label.parts.given[0]?.[0]) || []).filter((other) =>
      !other.ambiguous && !consumed.has(other) && compatible(label.parts, other.parts, true))
    // Pairwise agreement prevents a short name from connecting conflicting full names.
    const cluster = !label.ambiguous && neighbors.length && neighbors.every((a) => neighbors.every((b) => compatible(a.parts, b.parts, true))) ? neighbors : [label]
    const entries = cluster.flatMap((item) => item.entries)
    cluster.forEach((item) => consumed.add(item))
    const preferred = [...entries].sort((a, b) => b.display_name.length - a.display_name.length || a.entry_id.localeCompare(b.entry_id))[0]
    unresolved.push({ ...preferred, entry_type: 'schedule_name', professor_id: null,
      faculty_links: [], rmp: null, source_entries: entries, alias_ids: [], names: [] })
  }
  return [...known, ...unresolved].map((person) => ({ ...person,
    alias_ids: person.source_entries.map((entry) => entry.entry_id),
    names: [...new Set([person.display_name, ...person.source_entries.map((entry) => entry.display_name)])],
    subjects: [...new Set(person.source_entries.map((entry) => entry.subject))].sort(),
    courses: combineCourses([...(person.professor_id ? [person] : []), ...person.source_entries]),
  }))
}
