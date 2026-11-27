/* Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE. */
// Runs before first paint (loaded without defer) so the page never flashes the wrong theme.
(function () {
  var theme = null;
  try { theme = localStorage.getItem("cb-theme"); } catch (e) { /* storage blocked */ }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
