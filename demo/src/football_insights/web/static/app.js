// Minimal behavior for a server-rendered page: text zoom, copy-to-clipboard for
// trace IDs, expand all, a busy indicator for questions, and trace bar positions.
(function () {
  "use strict";
  var ZOOM_MIN = 14, ZOOM_MAX = 40, ZOOM_DEFAULT = 20;

  function applyZoom(px) {
    document.documentElement.style.fontSize = px + "px";
    try { localStorage.setItem("fiZoom", String(px)); } catch (e) { /* private mode */ }
  }
  function zoom(delta) {
    if (delta === 0) { applyZoom(ZOOM_DEFAULT); return; }
    var now = parseFloat(document.documentElement.style.fontSize) || ZOOM_DEFAULT;
    applyZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, now + delta)));
  }
  try {
    var saved = parseFloat(localStorage.getItem("fiZoom"));
    if (saved) { applyZoom(saved); }
  } catch (e) { /* ignore */ }

  document.addEventListener("click", function (event) {
    var target = event.target;
    var zoomButton = target.closest("[data-zoom]");
    if (zoomButton) { zoom(parseInt(zoomButton.getAttribute("data-zoom"), 10)); return; }
    var copy = target.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(copy.getAttribute("data-copy")).then(function () {
        copy.classList.add("copied");
        setTimeout(function () { copy.classList.remove("copied"); }, 1200);
      });
      return;
    }
    var expand = target.closest(".expand-all");
    if (expand) {
      var open = expand.textContent === "Expand all";
      document.querySelectorAll("main details").forEach(function (d) { d.open = open; });
      expand.textContent = open ? "Collapse all" : "Expand all";
    }
  });

  document.addEventListener("keydown", function (event) {
    var tag = event.target.tagName;
    if (event.ctrlKey || event.metaKey || event.altKey || tag === "INPUT" || tag === "TEXTAREA") { return; }
    if (event.key === "+" || event.key === "=") { zoom(2); }
    else if (event.key === "-") { zoom(-2); }
    else if (event.key === "0") { zoom(0); }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var button = form.querySelector("button[type=submit]");
    if (button) { button.disabled = true; button.textContent = "Thinking..."; }
    var busy = form.querySelector(".busy");
    if (busy) { busy.hidden = false; }
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".bar[data-left]").forEach(function (bar) {
      bar.style.left = bar.getAttribute("data-left") + "%";
      bar.style.width = bar.getAttribute("data-width") + "%";
    });
  });
})();
