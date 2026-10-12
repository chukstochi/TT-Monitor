(function () {
  var s = document.currentScript, p = s.getAttribute("data-project"), b = new URL(s.src).origin, vid;
  try {
    vid = localStorage.getItem("tt_vid");
    if (!vid) { vid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("tt_vid", vid); }
  } catch (e) { vid = "anon"; }
  function send(type, label) {
    var d = JSON.stringify({ project: p, type: type, vid: vid, label: (label || "").slice(0, 120) });
    if (navigator.sendBeacon) navigator.sendBeacon(b + "/api/track", d);
    else fetch(b + "/api/track", { method: "POST", body: d, keepalive: true });
  }
  window.ttTrack = send;                       // manual use: ttTrack("download", "android-apk")
  send("view", location.pathname);
  document.addEventListener("click", function (e) {
    var el = e.target.closest("a,button"); if (!el) return;
    var href = el.getAttribute("href") || "";
    var label = el.getAttribute("data-track") || (el.textContent || "").trim().slice(0, 60) || href;
    var dl = el.hasAttribute("data-download") || /\.(apk|ipa|exe|dmg|zip|pdf)(\?|$)/i.test(href);
    send(dl ? "download" : "click", label);
  }, true);
})();
