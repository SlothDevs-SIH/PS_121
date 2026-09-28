// Apply the saved theme/mode before first paint (no light flash in dark control rooms).
// Kept as an external file so the Content-Security-Policy can forbid inline scripts.
try {
  var t = localStorage.getItem('smriti.theme')
  var dark =
    t === 'dark' || (t !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  if (localStorage.getItem('smriti.mode') === 'field') {
    document.documentElement.dataset.mode = 'field'
  }
} catch (e) {
  // Storage blocked: the app falls back to defaults.
}
