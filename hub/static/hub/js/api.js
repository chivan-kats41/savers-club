// 1K Saver Club — talks to the Django REST API from the server-rendered pages.
//
// Pages are rendered from the database by Django (hub/selectors.py). Anything
// that CHANGES data goes through the real /api/v1/ endpoints, so every rule
// (ownership checks, stock reservation, OTPs, rate limits…) stays enforced on
// the server. This file only wires buttons/forms to those endpoints.
//
// Markup it understands
// ---------------------
//   <button data-api="/api/v1/member/offers/12/claim/">          POST, then reload
//   <button data-api="…" data-body='{"code":"1K-AB12"}'>          JSON body
//   <button data-api="…" data-confirm="Cancel this claim?">       confirm() first
//   <button data-api="…" data-prompt="otp" data-prompt-label="…"> ask for a value, send as body[otp]
//   <button data-api="…" data-after="none|reload|payment">        what to do on success
//   <form data-api="…">                                           fields → JSON body
//        name="checklist.phone_confirmed"  (dot = nested object)
//        data-number on an input/select    (send as a number)
//        data-ids on a multi-select        (send an array of numbers)
//   <button data-copy="1K-AB12">                                  copy text to clipboard
//
// Server errors ({"success": false, "error": {"message": …}}) are shown in a toast.

(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  // ---------------------------------------------------------------- toast --
  function toast(message, kind) {
    var host = document.getElementById("toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "toast-host";
      host.setAttribute("role", "status");
      host.setAttribute("aria-live", "polite");
      host.className = "fixed z-[100] bottom-20 lg:bottom-6 right-4 left-4 sm:left-auto sm:w-96 space-y-2 pointer-events-none";
      document.body.appendChild(host);
    }
    var el = document.createElement("div");
    var tone = kind === "error" ? "bg-destructive text-destructive-foreground" : "bg-foreground text-background";
    el.className = "pointer-events-auto rounded-xl px-4 py-3 text-sm shadow-lg " + tone;
    el.textContent = message; // textContent: never inject server text as HTML
    host.appendChild(el);
    setTimeout(function () { el.remove(); }, kind === "error" ? 7000 : 4000);
  }

  // ------------------------------------------------------------------ api --
  async function api(url, opts) {
    opts = opts || {};
    var method = (opts.method || "POST").toUpperCase();
    var init = {
      method: method,
      credentials: "same-origin",
      headers: { "Accept": "application/json", "X-CSRFToken": csrfToken() },
    };
    if (opts.body instanceof FormData) {
      init.body = opts.body; // browser sets the multipart boundary itself
    } else if (opts.body !== undefined && method !== "GET") {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    var res = await fetch(url, init);
    var payload = null;
    try { payload = await res.json(); } catch (e) { /* empty / non-JSON body */ }

    if (res.status === 401 || (res.status === 403 && payload && /credentials|authenticat/i.test(JSON.stringify(payload)))) {
      window.location.href = "/accounts/login/?next=" + encodeURIComponent(window.location.pathname);
      throw new Error("Please sign in again.");
    }
    if (!res.ok || (payload && payload.success === false)) {
      var err = (payload && payload.error) || {};
      var msg = err.message || (payload && payload.detail) || "Something went wrong (" + res.status + ").";
      var e2 = new Error(msg);
      e2.status = res.status;
      e2.payload = payload;
      throw e2;
    }
    return payload;
  }

  // ----------------------------------------------------------- form → JSON --
  function setPath(obj, path, value) {
    var parts = path.split(".");
    var cur = obj;
    for (var i = 0; i < parts.length - 1; i++) {
      cur = cur[parts[i]] = cur[parts[i]] || {};
    }
    cur[parts[parts.length - 1]] = value;
  }

  function formToJson(form) {
    var body = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled || el.type === "file") return;
      var v;
      if (el.type === "checkbox") {
        v = el.checked;
      } else if (el.type === "radio") {
        if (!el.checked) return;
        v = el.value;
      } else if (el.tagName === "SELECT" && el.multiple) {
        v = Array.prototype.filter.call(el.options, function (o) { return o.selected; }).map(function (o) { return o.value; });
        if (el.hasAttribute("data-ids")) v = v.map(Number);
      } else {
        v = el.value.trim();
        if (v === "") return; // let the server apply its own defaults/validation
        if (el.hasAttribute("data-number")) v = Number(v);
        if (el.type === "datetime-local") v = new Date(v).toISOString();
      }
      setPath(body, el.name, v);
    });
    return body;
  }

  // ------------------------------------------------------- after-success --
  function pollPayment(paymentId) {
    var tries = 0;
    toast("Approve the payment on your phone. We'll update this page when it goes through.");
    var timer = setInterval(async function () {
      tries += 1;
      try {
        var r = await api("/api/v1/payments/" + paymentId + "/", { method: "GET" });
        var status = r.data && r.data.status;
        if (status === "success") { clearInterval(timer); toast("Payment received. Thank you!"); setTimeout(function () { location.reload(); }, 900); }
        else if (status === "failed" || status === "cancelled" || status === "expired") { clearInterval(timer); toast("Payment was not completed (" + status + ").", "error"); }
      } catch (e) { /* keep polling */ }
      if (tries >= 30) { clearInterval(timer); toast("Still waiting for the provider. Refresh in a minute to see the result."); }
    }, 4000);
  }

  function afterSuccess(el, result) {
    var mode = el.getAttribute("data-after") || "reload";
    var msg = el.getAttribute("data-success");
    var data = result && result.data;

    if (mode === "payment" && data) {
      if (data.redirect_url) { window.location.href = data.redirect_url; return; }
      pollPayment(data.id);
      return;
    }
    if (msg) toast(msg.replace("{code}", (data && data.code) || ""));
    else if (data && data.code && /claim/.test(el.getAttribute("data-api") || "")) toast("Claimed! Your code is " + data.code);
    if (mode === "none") return;
    setTimeout(function () { window.location.reload(); }, msg || (data && data.code) ? 1200 : 300);
  }

  // A form with a file input is sent as multipart (e.g. ID documents).
  function hasFile(form) {
    return Array.prototype.some.call(form.elements, function (e) { return e.type === "file" && e.files && e.files.length; });
  }

  async function run(el, url, method, body) {
    var busy = el.tagName === "FORM" ? el.querySelector('[type="submit"]') : el;
    var label = busy && busy.textContent;
    if (busy) { busy.disabled = true; busy.setAttribute("aria-busy", "true"); }
    try {
      var multipart = el.tagName === "FORM" && hasFile(el) && !el.hasAttribute("data-upload-url");
      var payload = body;
      if (multipart) {
        payload = new FormData(el);
      }
      var result = await api(url, { method: method, body: payload });
      // Two-step create (offer + photo): send the file to a second endpoint using the new id.
      var upUrl = el.tagName === "FORM" && el.getAttribute("data-upload-url");
      if (upUrl) {
        var input = el.querySelector('input[type="file"]');
        if (input && input.files && input.files[0] && result.data && result.data.id) {
          var fd = new FormData();
          fd.append(input.getAttribute("data-upload-field") || "image", input.files[0]);
          try { await api(upUrl.replace("{id}", result.data.id), { method: "POST", body: fd }); }
          catch (e2) { toast("Saved, but the photo failed: " + e2.message, "error"); }
        }
      }
      afterSuccess(el, result);
    } catch (e) {
      toast(e.message, "error");
      if (busy) { busy.disabled = false; busy.removeAttribute("aria-busy"); if (label) busy.textContent = label; }
    }
  }

  // ------------------------------------------------------------- handlers --
  document.addEventListener("click", function (ev) {
    var copy = ev.target.closest("[data-copy]");
    if (copy) {
      ev.preventDefault();
      var text = copy.getAttribute("data-copy");
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(
        function () { toast("Copied " + text); },
        function () { toast("Copy failed — long-press the code to copy.", "error"); }
      );
      return;
    }

    var el = ev.target.closest("[data-api]");
    if (!el || el.tagName === "FORM") return;
    ev.preventDefault();

    var confirmMsg = el.getAttribute("data-confirm");
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    var body;
    var raw = el.getAttribute("data-body");
    if (raw) {
      try { body = JSON.parse(raw); } catch (e) { toast("Bad button configuration.", "error"); return; }
    }
    var promptKey = el.getAttribute("data-prompt");
    if (promptKey) {
      var answer = window.prompt(el.getAttribute("data-prompt-label") || "Enter a value");
      if (answer === null) return;
      answer = answer.trim();
      if (!answer) { toast("A value is required.", "error"); return; }
      body = body || {};
      body[promptKey] = answer;
    }
    run(el, el.getAttribute("data-api"), el.getAttribute("data-method") || "POST", body);
  });

  document.addEventListener("submit", function (ev) {
    var form = ev.target.closest("form[data-api]");
    if (!form) return;
    ev.preventDefault();
    var confirmMsg = form.getAttribute("data-confirm");
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    run(form, form.getAttribute("data-api"), form.getAttribute("data-method") || "POST", formToJson(form));
  });

  // Record call / WhatsApp / view clicks for merchant stats. Never blocks the click.
  document.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-track]");
    if (!el) return;
    var id = el.getAttribute("data-offer");
    if (!id) return;
    try {
      fetch("/api/v1/member/offers/" + id + "/interact/", {
        method: "POST", credentials: "same-origin", keepalive: true,
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ kind: el.getAttribute("data-track") }),
      });
    } catch (e) { /* tracking is best-effort */ }
  });

  window.SaverAPI = { api: api, toast: toast };
})();
