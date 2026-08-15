// Fixture: callback references passed as call arguments.
// Two registration styles must both keep the handler "referenced":
//   1. from inside a named function (setupUI)
//   2. from IIFE / module toplevel init code (attributed to the File node)

function onEvent() {
  return 42;
}

function setupUI() {
  document.addEventListener("click", onEvent);
  window.setTimeout(onEvent, 100);
}

(function () {
  var el = document.getElementById("go");
  el.addEventListener("input", onEvent);
})();
