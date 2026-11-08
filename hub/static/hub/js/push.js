/* Web Push opt-in. Shows [data-push-card] only where the browser supports push AND the site has VAPID keys configured.
   Nothing is subscribed until the person presses "Turn on alerts" (and the browser's own permission prompt is accepted). */
(function () {
  "use strict";
  var API = window.SaverAPI;
  var cfg = document.getElementById("geo-config");

  function $(sel, root) { return (root || document).querySelector(sel); }
  function toast(m) { if (API && API.toast) { API.toast(m); } else { window.alert(m); } }
  function call(url, method, body) { return API.api(url, { method: method || "GET", body: body }).then(function (p) { return p.data || {}; }); }

  function keyToBytes(b64) {
    var pad = "=".repeat((4 - b64.length % 4) % 4);
    var raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) { out[i] = raw.charCodeAt(i); }
    return out;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var card = $("[data-push-card]");
    if (!card || !API || !cfg) { return; }
    var vapid = cfg.getAttribute("data-vapid") || "";
    var statusNode = $("[data-push-status]", card);
    var enableBtn = $("[data-push-enable]", card), testBtn = $("[data-push-test]", card), disableBtn = $("[data-push-disable]", card);
    function say(t) { statusNode.textContent = t; }
    function show(btn, on) { if (btn) { btn.hidden = !on; } }

    if (!vapid) { return; }                       // site not configured for push: stay hidden
    card.hidden = false;
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      say("This browser doesn't support push alerts. On iPhone, add the site to your Home Screen first, then open it from there.");
      return;
    }

    var registration = null;
    function refresh() {
      if (Notification.permission === "denied") { say("Alerts are blocked for this site in your browser settings."); show(enableBtn, false); show(testBtn, false); show(disableBtn, false); return; }
      if (!registration) { return; }
      registration.pushManager.getSubscription().then(function (sub) {
        if (sub) { say("Alerts are on for this device."); show(enableBtn, false); show(testBtn, true); show(disableBtn, true); }
        else { say("Get deal and delivery alerts on this device, even when the site is closed."); show(enableBtn, true); show(testBtn, false); show(disableBtn, false); }
      });
    }
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (reg) { registration = reg; refresh(); })
      .catch(function () { say("Alerts can't be set up in this browser right now."); });

    enableBtn.addEventListener("click", function () {
      enableBtn.disabled = true;
      Notification.requestPermission().then(function (perm) {
        if (perm !== "granted") { throw new Error("Permission wasn't granted, so alerts stay off."); }
        return navigator.serviceWorker.ready;
      }).then(function (reg) {
        return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(vapid) });
      }).then(function (sub) {
        return call("/api/v1/push/subscribe/", "POST", JSON.parse(JSON.stringify(sub)));
      }).then(function () { toast("Alerts turned on."); refresh(); })
        .catch(function (e) { toast(e.message || "Couldn't turn on alerts."); })
        .then(function () { enableBtn.disabled = false; });
    });
    testBtn.addEventListener("click", function () {
      testBtn.disabled = true;
      call("/api/v1/push/test/", "POST").then(function () { toast("Test sent. It should arrive in a moment."); })
        .catch(function (e) { toast(e.message); }).then(function () { testBtn.disabled = false; });
    });
    disableBtn.addEventListener("click", function () {
      registration.pushManager.getSubscription().then(function (sub) {
        if (!sub) { return null; }
        var endpoint = sub.endpoint;
        return sub.unsubscribe().then(function () { return call("/api/v1/push/unsubscribe/", "POST", { endpoint: endpoint }); });
      }).then(function () { toast("Alerts turned off on this device."); refresh(); }).catch(function (e) { toast(e.message); });
    });
  });
})();
