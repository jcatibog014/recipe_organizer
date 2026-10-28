// Runs in <head>, before the page is drawn, so a saved dark theme doesn't
// flash light first. It's a file and not inline <script>, because our
// Content-Security-Policy blocks inline scripts.
// The "js" class lets CSS show things (like cook mode's one-step view) only when JavaScript runs.
document.documentElement.classList.add("js");
try {
  var savedTheme = localStorage.getItem("theme");
  if (savedTheme === "light" || savedTheme === "dark") {
    document.documentElement.dataset.theme = savedTheme;
  }
} catch (e) {
  // Private windows can block storage; then the system theme is used.
}
