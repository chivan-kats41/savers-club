/* Member page: a subscription payment that is still "pending".
   ioTec's callback cannot reach a local/dev server and the background sweep may not be running, so the page itself asks
   our API (which asks ioTec, the only authority) for the answer: once on load, every few seconds for a while, and
   whenever "Check status" is pressed. The browser never decides the outcome; it only displays what the server verified. */
(function () {
  "use strict";
  var btn = document.querySelector("[data-pending-check]");
  if (!btn) { return; }
  var text = document.querySelector("[data-pending-text]");
  var url = btn.getAttribute("data-status-url");
  var FINAL_BAD = ["failed", "cancelled", "expired", "refunded"];
  var tries = 0, MAX = 12, timer = null, busy = false;
  // overridable so tests can observe the reload
  var api = window.SaverPending = window.SaverPending || {};
  api.reload = api.reload || function () { window.location.reload(); };

  function say(msg) { if (text) { text.textContent = msg; } }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  function check(manual) {
    if (busy) { return; }
    busy = true; tries += 1;
    if (manual) { say("Checking with your payment provider…"); }
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (res) {
        if (res.status === 401 || res.status === 403) { window.location.href = "/accounts/login/?next=" + encodeURIComponent(location.pathname); return null; }
        return res.json();
      })
      .then(function (body) {
        if (!body || !body.data) { return; }
        var st = body.data.status;
        if (st === "success") { stop(); say("Payment received. Updating your account…"); setTimeout(api.reload, 900); return; }
        if (FINAL_BAD.indexOf(st) !== -1) {
          stop(); say("That payment was not completed and you weren't charged. Press Subscribe to try again.");
          btn.hidden = true; setTimeout(api.reload, 2500); return;
        }
        if (body.data.provider_check_failed) {
          say("We couldn't reach the payment provider just now. We'll keep trying; you don't need to pay again.");
        } else if (st === "requires_review") {
          say("We're still verifying this payment with your provider. If you approved it you don't need to pay again; we'll update this automatically.");
        } else if (manual || tries > 1) {
          say("Still waiting for your mobile-money provider to confirm. Approve the prompt on your phone if you haven't.");
        }
      })
      .catch(function () { /* network blip: the next tick tries again */ })
      .then(function () {
        busy = false;
        if (tries >= MAX) { stop(); }
      });
  }

  btn.addEventListener("click", function () { tries = 0; stop(); timer = setInterval(function () { check(false); }, 6000); check(true); });
  timer = setInterval(function () { check(false); }, 6000);
  check(false);
})();
