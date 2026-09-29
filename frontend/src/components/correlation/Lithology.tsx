/** SVG fill patterns for lithology (render once per page, reference by id). */
export function LithologyDefs() {
  const stroke = 'var(--text-muted)'
  return (
    <svg width="0" height="0" aria-hidden className="absolute">
      <defs>
        <pattern id="lith-sand" width="8" height="8" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="0.9" fill={stroke} opacity="0.55" />
          <circle cx="6" cy="6" r="0.9" fill={stroke} opacity="0.55" />
        </pattern>
        <pattern id="lith-clay" width="12" height="6" patternUnits="userSpaceOnUse">
          <path d="M 0 3 H 12" stroke={stroke} strokeWidth="0.8" opacity="0.5" />
        </pattern>
        <pattern id="lith-shale" width="10" height="6" patternUnits="userSpaceOnUse">
          <path d="M 1 3 H 6" stroke={stroke} strokeWidth="0.9" opacity="0.55" />
        </pattern>
        <pattern id="lith-lime" width="12" height="8" patternUnits="userSpaceOnUse">
          <path
            d="M 0 0 H 12 M 0 4 H 12 M 3 0 V 4 M 9 4 V 8"
            stroke={stroke}
            strokeWidth="0.7"
            opacity="0.5"
          />
        </pattern>
        <pattern id="lith-igneous" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M 3 3 L 7 7 M 7 3 L 3 7" stroke={stroke} strokeWidth="0.8" opacity="0.55" />
        </pattern>
      </defs>
    </svg>
  )
}
