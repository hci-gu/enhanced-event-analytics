import { readAnalysisStream } from './analysis.ts'
import type { AnalysisState } from './analysis.ts'

export async function checkHealth(): Promise<void> {
  let response: Response
  try {
    response = await fetch('/api/health', {
      cache: 'no-store',
      signal: AbortSignal.timeout(10000),
    })
  } catch {
    throw new Error('Det gick inte att nå servern. Kontrollera att tjänsten är igång och försök igen.')
  }

  if (!response.ok) {
    throw new Error(`Hälsokontrollen misslyckades (HTTP ${response.status}).`)
  }

  let result: unknown
  try {
    result = await response.json()
  } catch {
    throw new Error('Hälsokontrollen gav ett ogiltigt svar från servern.')
  }

  if (typeof result !== 'object' || result === null || !('status' in result) || result.status !== 'ok') {
    throw new Error('Servern är inte redo. Hälsokontrollen rapporterade inte status "ok".')
  }
}

export async function streamAnalysis(
  text: string, onState: (state: AnalysisState) => void, signal?: AbortSignal,
): Promise<void> {
  const trimmedText = text.trim()
  if (!trimmedText) throw new Error('Skriv en händelsetext först.')

  let response: Response
  try {
    response = await fetch('/api/analyze-event/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ text: trimmedText }),
      signal,
    })
  } catch {
    throw new Error('Det gick inte att nå servern. Kontrollera anslutningen och försök igen.')
  }
  if (!response.ok) throw new Error(`Förfrågan misslyckades (HTTP ${response.status}). Försök igen.`)
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('Servern skickade ett ogiltigt analysflöde.')
  }
  await readAnalysisStream(response.body, onState)
}
