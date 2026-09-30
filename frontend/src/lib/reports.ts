/**
 * Offset Risk Brief download (master plan "Pre-spud Offset Risk Brief"; backend
 * `GET /api/v1/reports/offset-brief/{well_id}`, a PDF). The PDF is fetched as a blob on the
 * same origin, so the session cookie goes with it, and saved under the server's filename.
 */
import { ApiError, type ErrorBody } from './api/client'

export interface BriefProgress {
  received: number
  /** Content-Length when the server sent one, else null (progress is then bytes only). */
  total: number | null
}

export interface BriefFile {
  blob: Blob
  filename: string
}

/** The filename from a Content-Disposition header (RFC 6266: filename* wins), else null. */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*\s*=\s*([^;]+)/i.exec(header)
  if (star?.[1]) {
    const value = star[1].trim().replace(/^"|"$/g, '')
    const encoded = value.includes("''") ? value.slice(value.indexOf("''") + 2) : value
    try {
      return safeName(decodeURIComponent(encoded))
    } catch {
      // fall through to the plain parameter
    }
  }
  const plain = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(header)
  const name = plain?.[2] ?? plain?.[1]?.trim()
  return name ? safeName(name) : null
}

/** Strip path separators and control characters; never an empty name. */
function safeName(name: string): string | null {
  const clean = name
    .replace(/[/\\]/g, '_')
    // oxlint-disable-next-line no-control-regex -- stripping control characters is the point
    .replace(/[\x00-\x1f]/g, '')
    .trim()
  return clean || null
}

export function fallbackBriefName(wellName: string): string {
  return `SMRITI_offset_risk_brief_${wellName.replace(/[^A-Za-z0-9._-]+/g, '_')}.pdf`
}

async function errorFrom(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  const envelope =
    typeof body === 'object' && body !== null && 'error' in body
      ? (body as { error: ErrorBody }).error
      : null
  return new ApiError(
    response.status,
    envelope,
    `HTTP ${response.status} ${response.statusText}`.trim(),
  )
}

/** Fetch the brief, reporting bytes as they arrive. Errors arrive as ApiError (the
 * backend's envelope when it sent one, status 0 when the backend is unreachable). */
export async function fetchOffsetBrief(
  wellId: number,
  radiusKm: number,
  wellName: string,
  onProgress?: (p: BriefProgress) => void,
  signal?: AbortSignal,
): Promise<BriefFile> {
  let response: Response
  try {
    response = await fetch(
      `/api/v1/reports/offset-brief/${wellId}?radius_km=${encodeURIComponent(radiusKm)}`,
      {
        credentials: 'same-origin',
        headers: { Accept: 'application/pdf', 'X-Requested-With': 'smriti' },
        signal,
      },
    )
  } catch (cause) {
    if (signal?.aborted) throw cause
    throw new ApiError(0, null, `Backend unreachable: ${String(cause)}`)
  }
  if (!response.ok) throw await errorFrom(response)

  const length = Number(response.headers.get('Content-Length'))
  const total = Number.isFinite(length) && length > 0 ? length : null
  const type = response.headers.get('Content-Type') ?? 'application/pdf'
  let blob: Blob
  if (response.body) {
    const reader = response.body.getReader()
    const chunks: Uint8Array<ArrayBuffer>[] = []
    let received = 0
    onProgress?.({ received, total })
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value as Uint8Array<ArrayBuffer>)
      received += value.byteLength
      onProgress?.({ received, total })
    }
    blob = new Blob(chunks, { type })
  } else {
    blob = await response.blob()
    onProgress?.({ received: blob.size, total })
  }
  const filename =
    filenameFromDisposition(response.headers.get('Content-Disposition')) ??
    fallbackBriefName(wellName)
  return { blob, filename }
}

/** Hand a blob to the browser's download manager under `filename`. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revoke after the click has been handled (some browsers read the URL asynchronously).
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
