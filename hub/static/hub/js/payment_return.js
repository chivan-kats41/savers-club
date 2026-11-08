// Polls our own API (which verifies with ioTec) until the payment reaches a final state.
(function () {
  "use strict";
  var root = document.getElementById("pay-return");
  if (!root) return;
  var url = root.getAttribute("data-status-url");
  var msg = document.getElementById("pay-message");
  var box = document.getElementById("pay-state");
  var cont = document.getElementById("pay-continue");
  var retry = document.getElementById("pay-retry");
  var tries = 0, MAX = 30, timer = null;

  function show(text, tone) {
    msg.textContent = text; // textContent: never inject server text as HTML
    box.className = "mt-5 rounded-xl border p-4 text-sm " +
      (tone === "ok" ? "bg-primary-soft text-primary border-primary/30" :
       tone === "bad" ? "bg-destructive/10 text-destructive border-destructive/30" : "");
  }

  function finish(status) {
    clearInterval(timer);
    retry.classList.add("hidden");
    if (status === "success") {
      show("Payment received. Thank you! Your account has been updated.", "ok");
    } else if (status === "requires_review") {
      show("We received your payment but need to verify it. We'll notify you shortly; you don't need to pay again.", "");
    } else {
      show("The payment was not completed" + (status ? " (" + status.replace(/_/g, " ") + ")" : "") + ". You have not been charged for it. You can try again.", "bad");
    }
    cont.classList.remove("hidden");
  }

  async function check() {
    tries += 1;
    try {
      var res = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (res.status === 401 || res.status === 403) { window.location.href = "/accounts/login/?next=" + encodeURIComponent(location.pathname + location.search); return; }
      var body = await res.json();
      var status = body && body.data && body.data.status;
      if (["success", "failed", "cancelled", "expired", "refunded", "requires_review"].indexOf(status) !== -1) return finish(status);
      show(status === "sent_to_vendor" ? "Waiting for your card payment to be confirmed…" : "Waiting for confirmation…", "");
    } catch (e) { /* network blip: keep trying */ }
    if (tries >= MAX) {
      clearInterval(timer);
      show("It's taking longer than usual. Your payment may still complete: check again in a minute.", "");
      retry.classList.remove("hidden");
      cont.classList.remove("hidden");
    }
  }

  retry.addEventListener("click", function () { tries = 0; retry.classList.add("hidden"); show("Checking payment status…", ""); timer = setInterval(check, 3000); check(); });
  timer = setInterval(check, 3000);
  check();
})();
