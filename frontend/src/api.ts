export async function submitEvent(text: string): Promise<string> {
  const trimmedText = text.trim()
  if (!trimmedText) throw new Error('Skriv en händelsetext först.')

  let response: Response
  try {
    response = await fetch('/api/analyze-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: trimmedText }),
    })
  } catch {
    throw new Error('Det gick inte att nå servern. Kontrollera anslutningen och försök igen.')
  }

  if (!response.ok) {
    throw new Error(`Förfrågan misslyckades (HTTP ${response.status}). Försök igen.`)
  }

  let result: unknown
  try {
    result = await response.json()
  } catch {
    throw new Error('Servern skickade ett ogiltigt svar. Försök igen.')
  }

  if (
    typeof result !== 'object' || result === null ||
    !('status' in result) || result.status !== 'not_implemented' ||
    !('results' in result) || typeof result.results !== 'object' ||
    result.results === null || Array.isArray(result.results)
  ) {
    throw new Error('Servern skickade ett oväntat svar. Försök igen.')
  }

  return 'Texten har tagits emot. Analysfunktionen är inte tillgänglig ännu.'
}
