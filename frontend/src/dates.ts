export type DateField = 'published_at' | 'event_start' | 'event_end'
export type DateResults = {
  published_at: string | null
  event_start: string | null
  event_end: string | null
  end_status: 'dated' | 'until_further_notice' | 'unknown'
  duration_hint: string | null
  evidence: Record<DateField, string[]>
}

export function validDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?$/.test(value)) return false
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  return year > 0 && month >= 1 && month <= 12 && day >= 1 && day <= days
    && (value.length === 10 || (Number(value.slice(11, 13)) < 24 && Number(value.slice(14, 16)) < 60))
}

export function parseDateResults(value: unknown): DateResults | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  const data = value as Record<string, unknown>
  if (!['dated', 'until_further_notice', 'unknown'].includes(String(data.end_status))) return null
  const evidence = data.evidence
  if (typeof evidence !== 'object' || evidence === null || Array.isArray(evidence)) return null
  const quotes = evidence as Record<string, unknown>
  const fields = ['published_at', 'event_start', 'event_end'] as const
  if (fields.some((field) => !Array.isArray(quotes[field]) || quotes[field].some((quote) => typeof quote !== 'string'))) return null
  const result: DateResults = {
    published_at: validDate(data.published_at) ? data.published_at : null,
    event_start: validDate(data.event_start) ? data.event_start : null,
    event_end: validDate(data.event_end) ? data.event_end : null,
    end_status: data.end_status as DateResults['end_status'],
    duration_hint: typeof data.duration_hint === 'string' && /^~[1-9][0-9]*[HDWMY]$/.test(data.duration_hint) ? data.duration_hint : null,
    evidence: Object.fromEntries(fields.map((field) => [field, quotes[field]])) as DateResults['evidence'],
  }
  return fields.some((field) => result[field] !== null) ? result : null
}

// Preserve the source's calendar date and time instead of converting an unspecified timezone.
export function displaySourceDate(value: string): string {
  const months = ['jan', 'feb', 'mars', 'apr', 'maj', 'juni', 'juli', 'aug', 'sep', 'okt', 'nov', 'dec']
  const [, month, day] = value.slice(0, 10).split('-').map(Number)
  return `${day} ${months[month - 1]}${value.includes('T') ? ` · ${value.slice(11, 16)}` : ''}`
}

export function datePosition(value: string): number {
  return Date.parse(value.length === 10 ? `${value}T00:00:00Z`
    : /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}:00Z`)
}

export function displayDuration(hint: string): string {
  const amount = Number(hint.slice(1, -1))
  const units: Record<string, [string, string]> = {
    H: ['timme', 'timmar'], D: ['dag', 'dagar'], W: ['vecka', 'veckor'], M: ['månad', 'månader'], Y: ['år', 'år'],
  }
  return `~${amount} ${units[hint.at(-1)!][amount === 1 ? 0 : 1]}`
}
