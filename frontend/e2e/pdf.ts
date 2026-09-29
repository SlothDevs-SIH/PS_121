/** Build a small valid one-page PDF with Helvetica text lines (correct xref offsets). */
export function makePdf(lines: string[]): Buffer {
  const esc = (s: string) => s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')
  const content =
    'BT /F1 12 Tf 72 780 Td 16 TL\n' + lines.map((l) => `(${esc(l)}) Tj T*`).join('\n') + '\nET'
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  let out = '%PDF-1.4\n'
  const offsets: number[] = []
  objects.forEach((body, i) => {
    offsets.push(Buffer.byteLength(out))
    out += `${i + 1} 0 obj\n${body}\nendobj\n`
  })
  const xref = Buffer.byteLength(out)
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  out += offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('')
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(out, 'latin1')
}

/** The daily report the backend's B2 integration test uses to land an event in review: the
 * NPT row names no problem and no depth unit, so extraction can't be confident. The date and
 * depth differ from that test's report so the two events are never merged. */
export function lowConfidenceDdr(nonce: string, date = '2021-06-10'): Buffer {
  return makePdf([
    'DAILY DRILLING REPORT',
    'SYNTHETIC DATA - NOT OIL INDIA DATA',
    `Well: SYN-ASM-01    Rig: Rig SYN-1    Report No: 96    Date: ${date}`,
    `Depth at 24:00: 1,500 m    Hole size: 12-1/4 in    Nonce ${nonce}`,
    'TIME LOG',
    'From  To  Hrs  Depth (m)  Code  Operation',
    '00:00  06:00  6.0  1495  DRL  Drilled ahead',
    '06:00  09:00  3.0  1495  NPT-LOSS  Operations suspended',
    '09:00  24:00  15.0  1495  CIRC  Circulated',
    'REMARKS',
    'See time log.',
  ])
}
