/* "Send code" for withdrawals: asks the server to text a one-time code to the phone on the ACCOUNT.
   The code is checked on the server when the withdrawal is submitted; this script only requests and times the resend. */
(function () {
  "use strict";
  var API = window.SaverAPI;
  if (!API) { return; }
  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.slice.call(document.querySelectorAll("[data-withdraw-code]")).forEach(function (btn) {
      var form = btn.closest("form");
      var note = (form && form.parentNode.querySelector("[data-withdraw-code-note]")) || null;
      var label = btn.textContent, timer = null;
      function say(t) { if (note) { note.textContent = t; } else { API.toast(t); } }
      function cooldown(seconds) {
        var left = seconds; btn.disabled = true;
        timer = setInterval(function () {
          left -= 1; btn.textContent = "Resend in " + left + "s";
          if (left <= 0) { clearInterval(timer); btn.disabled = false; btn.textContent = "Resend code"; }
        }, 1000);
        btn.textContent = "Resend in " + left + "s";
      }
      btn.addEventListener("click", function () {
        btn.disabled = true; btn.textContent = "Sending…";
        API.api("/api/v1/withdraw/code/", { method: "POST", body: {} }).then(function (p) {
          var d = p.data || {};
          say("Code sent to the phone on your account (" + (d.phone_hint || "…") + "). It expires in 10 minutes." +
              (d.dev_code ? "  [DEV ONLY] code: " + d.dev_code : ""));
          cooldown(45);
        }).catch(function (e) { say(e.message || "Couldn't send the code."); btn.disabled = false; btn.textContent = label; });
      });
    });
  });
})();
