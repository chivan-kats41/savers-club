// Location sharing for geo-locking. Talks to /api/v1/geo/location/ (see hub/geo_api.py).
//
// Rules this file follows:
//  * It only asks the browser for permission when the person presses a button (a user gesture), or when permission
//    was ALREADY granted (then it refreshes silently so nearby results stay current).
//  * Geolocation needs a secure context (https or localhost). Otherwise we explain and point to the area fallback.
//  * Nothing is stored in the browser. The server keeps one rounded, latest point per person.
(function () {
  "use strict";

  function supported() { return window.isSecureContext && "geolocation" in navigator; }

  function explain(err) {
    if (!err) return "Couldn't get your location.";
    if (err.code === 1) return "Location is blocked for this site. Allow it in your browser's site settings (the lock icon beside the address), or choose your area instead.";
    if (err.code === 2) return "Your device couldn't work out where you are. Turn on location services, or choose your area instead.";
    if (err.code === 3) return "Finding your location took too long. Try again, or choose your area instead.";
    return err.message || "Couldn't get your location.";
  }

  function position(opts) {
    return new Promise(function (resolve, reject) { navigator.geolocation.getCurrentPosition(resolve, reject, opts); });
  }

  async function share(role) {
    if (!supported()) {
      throw new Error("Location needs a secure connection (https) and a browser that supports it. Choose your area instead.");
    }
    var pos;
    try { pos = await position({ enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }); }
    catch (e) { throw new Error(explain(e)); }
    var r = await window.SaverAPI.api("/api/v1/geo/location/", {
      method: "POST",
      body: { role: role, lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy },
    });
    return r.data;
  }

  // Reload goes through a hook so it can be replaced (the browser tests do this).
  var hooks = { reload: function () { window.location.reload(); } };
  function reloadSoon() { setTimeout(function () { hooks.reload(); }, 400); }

  // ---- "Share / update my location" buttons -----------------------------------------------------------------
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-geo-locate]");
    if (!btn) return;
    ev.preventDefault();
    var role = btn.getAttribute("data-geo-role") || "member";
    var label = btn.textContent;
    btn.disabled = true; btn.textContent = "Finding you…";
    share(role).then(function (data) {
      window.SaverAPI.toast(role === "merchant" ? "Shop location saved." : "Location updated.");
      if (btn.hasAttribute("data-geo-reload") || data.changed) reloadSoon();
      else { btn.disabled = false; btn.textContent = label; }
    }).catch(function (e) {
      window.SaverAPI.toast(e.message, "error");
      btn.disabled = false; btn.textContent = label;
    });
  });

  function permissionState() {
    if (!navigator.permissions || !navigator.permissions.query) return Promise.resolve("unknown");
    return navigator.permissions.query({ name: "geolocation" }).then(function (p) { return p.state; }, function () { return "unknown"; });
  }

  // ---- members: silent refresh when permission was already granted ------------------------------------------
  function autoMember(el) {
    if (!supported()) return;
    var age = parseInt(el.getAttribute("data-geo-age"), 10);           // seconds since the stored point; NaN = none
    if (!isNaN(age) && age < 300) return;                              // fresh enough
    permissionState().then(function (state) {
      if (state !== "granted") return;
      share("member").then(function (data) {
        var last = parseInt(sessionStorage.getItem("geoReloadAt") || "0", 10);
        if (data.changed && Date.now() - last > 120000) {              // never reload-loop
          sessionStorage.setItem("geoReloadAt", String(Date.now()));
          hooks.reload();
        }
      }).catch(function () { /* silent: the bar still offers the manual button */ });
    });
  }

  // ---- riders: live location while the page is open ---------------------------------------------------------
  function watchRider(el) {
    var out = document.getElementById("geo-rider-status");
    var lastSent = 0, busy = false, first = true;
    function say(t) { if (out) out.textContent = t; }
    if (!supported()) { say("Location needs a secure connection (https)."); return; }
    permissionState().then(function (state) {
      if (state === "denied") { say("Location is blocked. Allow it in your browser's site settings."); return; }
      if (state === "prompt" && !el.hasAttribute("data-geo-prompt")) { say("Press “Share my location” to start."); return; }
      navigator.geolocation.watchPosition(function (pos) {
        var now = Date.now();
        if (busy || now - lastSent < 30000) return;
        busy = true; lastSent = now;
        window.SaverAPI.api("/api/v1/geo/location/", { method: "POST", body: {
          role: "rider", lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy } })
          .then(function (r) { say("Sharing your live location. Updated just now."); if (first && r.data.changed) { first = false; if (el.getAttribute("data-geo-state") !== "live") reloadSoon(); } })
          .catch(function (e) { say(e.message); })
          .then(function () { busy = false; });
      }, function (err) { say(explain(err)); }, { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var m = document.querySelector('[data-geo-auto="member"]'); if (m) autoMember(m);
    var r = document.querySelector('[data-geo-watch="rider"]'); if (r) watchRider(r);
  });

  window.SaverGeo = { share: share, supported: supported, hooks: hooks };
})();
