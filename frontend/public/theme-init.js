// Apply the saved theme/mode before first paint (no light flash in dark control rooms).
// Kept as an external file so the Content-Security-Policy can forbid inline scripts.
// Mirrors initialTheme() in src/stores/ui.ts (including Part 1's saved 'light'/'dark').
try {
  var t = localStorage.getItem('smriti.theme')
  var theme =
    t === 'daylight' || t === 'light'
      ? 'daylight'
      : t === 'command-blue'
        ? 'command-blue'
        : 'deep-rig'
  document.documentElement.dataset.theme = theme
  if (localStorage.getItem('smriti.mode') === 'field') {
    document.documentElement.dataset.mode = 'field'
  }
} catch (e) {
  document.documentElement.dataset.theme = 'deep-rig'
}
