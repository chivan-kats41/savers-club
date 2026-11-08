/* 1K Saver Club: location features (vanilla JS, no build step).
   - deals "near me" + map view            [data-deals-map] [data-geo-locate] [data-hot-grid]
   - location & history settings           [data-geo-setting] [data-geo-area] [data-geo-clear] [data-geo-del]
   - drop-off address search + pin         [data-geocode]
   - delivery tracking (member / rider)    [data-track-url] [data-nav-url]
   - rider live position sharing           [data-rider-share]
   - shop pin (merchant)                   [data-shop-pin]
   All text from the server is inserted with textContent (never innerHTML). Network calls go to our own API only. */
(function () {
  "use strict";

  var API = window.SaverAPI;
  var cfg = document.getElementById("geo-config");
  var hasLeaflet = typeof window.L !== "undefined";

  // ------------------------------------------------------------------ helpers --
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = text; }
    return n;
  }
  function toast(msg) { if (API && API.toast) { API.toast(msg); } else { window.alert(msg); } }
  function call(url, method, body) {
    return API.api(url, { method: method || "GET", body: body }).then(function (p) { return p.data || {}; });
  }
  function fail(err) { toast((err && err.message) || "Something went wrong."); }
  function ugx(n) { return "UGX " + Math.round(Number(n) || 0).toLocaleString("en-UG"); }
  function debounce(fn, ms) { var t; return function () { var a = arguments, c = this; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); }; }
  function num(v) { var n = parseFloat(v); return isFinite(n) ? n : null; }
  function qs(obj) {
    return Object.keys(obj).filter(function (k) { return obj[k] !== null && obj[k] !== undefined && obj[k] !== ""; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(obj[k]); }).join("&");
  }
  function clock(iso) {
    try { return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); } catch (e) { return ""; }
  }
  function store(key, val) { try { if (val === null) { localStorage.removeItem(key); } else { localStorage.setItem(key, val); } } catch (e) { /* private mode */ } }
  function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }

  /** Ask the browser for the current position. Resolves {lat, lng, accuracy}. */
  function locate() {
    return new Promise(function (resolve, reject) {
      if (!navigator.geolocation) { reject(new Error("This browser can't share its location.")); return; }
      navigator.geolocation.getCurrentPosition(function (p) {
        resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy });
      }, function (e) {
        reject(new Error(e && e.code === 1
          ? "Location permission was denied. You can still pick your area by hand."
          : "Couldn't get your location. Try again, or pick your area by hand."));
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
    });
  }

  // ------------------------------------------------------------------ map kit --
  function pin(kind, glyph) {
    var n = el("div", "geo-pin" + (kind ? " geo-pin-" + kind : ""), glyph || "");
    return L.divIcon({ html: n, className: "", iconSize: kind === "me" ? [18, 18] : [34, 34], iconAnchor: kind === "me" ? [9, 9] : [17, 17], popupAnchor: [0, -14] });
  }
  function makeMap(node, center, zoom) {
    if (!hasLeaflet) { node.textContent = "The map could not be loaded."; return null; }
    var c = center || [num(cfg && cfg.dataset.centerLat) || 0.3476, num(cfg && cfg.dataset.centerLng) || 32.5825];
    var map = L.map(node, { scrollWheelZoom: false }).setView(c, zoom || 13);
    // Tile servers (OpenStreetMap) block requests with no Referer. The page's own policy sends none to other sites, so
    // the tile images alone send the bare origin. See MAP_TILE_REFERRER_POLICY.
    L.tileLayer(cfg.dataset.tileUrl, {
      maxZoom: 19, attribution: cfg.dataset.attribution || "",
      referrerPolicy: cfg.dataset.tileReferrer || false
    }).addTo(map);
    return map;
  }
  /** Leaflet measures its container once: when a hidden map is revealed it must be told. */
  function reveal(map) { if (map) { setTimeout(function () { map.invalidateSize(); }, 60); } }

  // ------------------------------------------------------------------ deals map --
  function DealsMap(node) {
    this.node = node;
    this.map = makeMap(node);
    this.layer = this.map ? L.layerGroup().addTo(this.map) : null;
    this.openUrl = node.getAttribute("data-open-url") || "";
  }
  DealsMap.prototype.update = function (data) {
    if (!this.map) { return; }
    var self = this, pts = [];
    this.layer.clearLayers();
    var o = data && data.origin;
    if (o && o.lat !== null && o.lat !== undefined) {
      L.marker([o.lat, o.lng], { icon: pin("me"), title: "You" }).addTo(this.layer);
      pts.push([o.lat, o.lng]);
    }
    ((data && data.deals) || []).forEach(function (d) {
      if (d.lat === null || d.lat === undefined) { return; }
      var m = L.marker([d.lat, d.lng], { icon: pin("", d.emoji || "🏷️"), title: d.item });
      var body = el("div", "geo-pop");
      body.appendChild(el("strong", "", d.item));
      body.appendChild(el("span", "", d.seller + (d.area ? " · " + d.area : "")));
      body.appendChild(el("span", "", ugx(d.member) + "  (save " + ugx(d.saving) + ")"));
      if (d.distance) { body.appendChild(el("span", "", d.distance)); }
      if (!d.precise) { body.appendChild(el("span", "", "Approximate position (seller has not pinned the shop yet)")); }
      if (self.openUrl) { var a = el("a", "", "Open in app"); a.href = self.openUrl; a.style.fontSize = "0.75rem"; body.appendChild(a); }
      m.bindPopup(body);
      m.addTo(self.layer);
      pts.push([d.lat, d.lng]);
    });
    if (pts.length > 1) { this.map.fitBounds(pts, { padding: [30, 30], maxZoom: 15 }); }
    else if (pts.length === 1) { this.map.setView(pts[0], 15); }
    else if (data && data.center) { this.map.setView(data.center, 13); }
  };

  function readJson(id) {
    var n = document.getElementById(id);
    if (!n) { return null; }
    try { return JSON.parse(n.textContent); } catch (e) { return null; }
  }

  function dealCard(d) {
    var card = el("div", "rounded-2xl border bg-card p-4");
    var top = el("div", "flex items-start gap-3");
    top.appendChild(el("div", "h-12 w-12 rounded-xl bg-muted flex items-center justify-center text-xl", d.emoji || "🏷️"));
    var info = el("div", "flex-1 min-w-0");
    info.appendChild(el("div", "font-medium", d.item));
    info.appendChild(el("div", "text-xs text-muted-foreground truncate", d.seller + " · " + d.vendorType));
    info.appendChild(el("div", "text-xs text-muted-foreground", "📍 " + d.area + (d.distance ? " · " + d.distance : "")));
    top.appendChild(info);
    card.appendChild(top);
    var bottom = el("div", "mt-3 flex items-end justify-between");
    var price = el("div");
    var p = el("div", "text-base font-semibold text-primary", ugx(d.member) + " ");
    p.appendChild(el("span", "text-xs line-through text-muted-foreground font-normal", ugx(d.normal)));
    price.appendChild(p);
    price.appendChild(el("div", "text-[11px] text-primary font-medium", "You save " + ugx(d.saving)));
    bottom.appendChild(price);
    var badges = el("div", "flex flex-wrap justify-end gap-1");
    badges.style.maxWidth = "55%";
    (d.badges || []).slice(0, 2).forEach(function (b) { badges.appendChild(el("span", "text-[10px] px-1.5 py-0.5 rounded bg-accent-soft text-accent font-semibold", b)); });
    bottom.appendChild(badges);
    card.appendChild(bottom);
    return card;
  }

  function initDeals() {
    var nodes = $$("[data-deals-map]");
    var maps = nodes.map(function (n) {
      var m = new DealsMap(n);
      var data = readJson(n.getAttribute("data-source") || "");
      if (data) { m.update(data); }
      return m;
    });

    // list / map toggle
    $$("[data-view-toggle]").forEach(function (group) {
      var scope = group.closest("[data-view-scope]") || document;
      $$("button[data-view-target]", group).forEach(function (btn) {
        btn.addEventListener("click", function () {
          var target = btn.getAttribute("data-view-target");
          $$("button[data-view-target]", group).forEach(function (b) { b.setAttribute("aria-pressed", b === btn ? "true" : "false"); });
          $$("[data-view]", scope).forEach(function (v) { v.hidden = v.getAttribute("data-view") !== target; });
          if (target === "map") { maps.forEach(function (m) { reveal(m.map); }); }
        });
      });
    });

    // "Use my location"
    $$("[data-geo-locate]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var original = btn.textContent;
        btn.disabled = true; btn.textContent = "Finding you…";
        var signedIn = btn.getAttribute("data-authenticated") === "1";
        var mode = btn.getAttribute("data-geo-locate") || "landing";
        locate().then(function (pos) {
          var ping = signedIn ? call("/api/v1/geo/me/ping/", "POST", { lat: pos.lat, lng: pos.lng, accuracy: pos.accuracy }) : Promise.resolve({ stored: false });
          return ping.then(function (res) {
            if (mode === "member" && res.stored) { window.location.reload(); return null; }
            return call("/api/v1/geo/nearby-deals/?" + qs({ lat: pos.lat, lng: pos.lng, limit: mode === "member" ? 12 : 6 }));
          });
        }).then(function (data) {
          if (!data) { return; }
          renderNearby(data);
          if (btn.getAttribute("data-geo-locate") === "member") {
            toast("Showing deals near you on the map. Turn on “Remember my location” below to rank your results by it.");
          }
        }).catch(fail).then(function () { btn.disabled = false; btn.textContent = original; });
      });
    });

    function renderNearby(data) {
      var label = data.origin ? data.origin.label : "";
      $$("[data-origin-label]").forEach(function (n) { n.textContent = label || "you"; });
      $$("[data-hot-heading]").forEach(function (n) { n.textContent = label ? "Hot deals · " + label : "Today's hot deals"; });
      $$("[data-hot-sub]").forEach(function (n) {
        n.textContent = data.origin && data.origin.precise ? "Ranked by distance from where you are right now, then savings and how soon they end." : "Live offers from verified sellers.";
      });
      $$("[data-hot-grid]").forEach(function (grid) {
        grid.textContent = "";
        if (!data.deals.length) { grid.appendChild(el("div", "rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground", "No deals near this spot right now. Try again later or pick another area.")); }
        data.deals.forEach(function (d) { grid.appendChild(dealCard(d)); });
      });
      maps.forEach(function (m) { m.update({ origin: data.origin, deals: data.deals, center: data.origin && data.origin.lat ? [data.origin.lat, data.origin.lng] : null }); });
    }
  }

  // ------------------------------------------------------------------ location settings --
  function initSettings() {
    function patch(body) { return call("/api/v1/geo/me/", "PATCH", body); }
    $$("[data-geo-setting]").forEach(function (box) {
      box.addEventListener("change", function () {
        var key = box.getAttribute("data-geo-setting");
        var body = {}; body[key] = box.checked;
        box.disabled = true;
        patch(body).then(function () {
          if (key === "share_location" && box.checked) {
            return locate().then(function (pos) {
              return call("/api/v1/geo/me/ping/", "POST", { lat: pos.lat, lng: pos.lng, accuracy: pos.accuracy });
            }).catch(function (e) { toast(e.message); });
          }
        }).then(function () { window.location.reload(); }).catch(function (e) { box.checked = !box.checked; box.disabled = false; fail(e); });
      });
    });
    $$("[data-geo-area]").forEach(function (sel) {
      sel.addEventListener("change", function () {
        patch({ area_override: sel.value || null }).then(function () { window.location.reload(); }).catch(fail);
      });
    });
    $$("[data-geo-clear]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!window.confirm("Delete your whole location history? This can't be undone.")) { return; }
        call("/api/v1/geo/me/history/", "DELETE").then(function () { window.location.reload(); }).catch(fail);
      });
    });
    $$("[data-geo-del]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        call("/api/v1/geo/me/history/" + encodeURIComponent(btn.getAttribute("data-geo-del")) + "/", "DELETE")
          .then(function () { var li = btn.closest("li"); if (li) { li.remove(); } }).catch(fail);
      });
    });
    // simple notification preference checkboxes (e.g. hot-deal alerts)
    $$("[data-pref]").forEach(function (box) {
      box.addEventListener("change", function () {
        var body = {}; body[box.getAttribute("data-pref")] = box.checked;
        call(box.getAttribute("data-pref-url"), "PATCH", body).then(function () {
          toast(box.checked ? "Saved. You'll get at most one hot-deal alert a day." : "Deal alerts turned off.");
        }).catch(function (e) { box.checked = !box.checked; fail(e); });
      });
    });
    // trail map
    $$("[data-trail-map]").forEach(function (node) {
      var pts = readJson(node.getAttribute("data-source") || "") || [];
      var map = makeMap(node, pts.length ? [pts[0].lat, pts[0].lng] : null, 13);
      if (!map) { return; }
      var latlngs = pts.map(function (p) { return [p.lat, p.lng]; });
      pts.forEach(function (p, i) {
        var m = L.marker([p.lat, p.lng], { icon: pin(i === 0 ? "" : "me", i === 0 ? "📍" : ""), title: p.label });
        m.bindPopup(el("div", "geo-pop", p.label + (p.when ? " · " + p.when : "")));
        m.addTo(map);
      });
      if (latlngs.length > 1) { L.polyline(latlngs, { color: "#2563eb", weight: 2, opacity: 0.6, dashArray: "4 6" }).addTo(map); map.fitBounds(latlngs, { padding: [30, 30], maxZoom: 15 }); }
      var wrap = node.closest("[data-trail-wrap]");
      if (wrap) { wrap.addEventListener("toggle", function () { reveal(map); }); }
    });
  }

  // ------------------------------------------------------------------ address search --
  /** Wire an input to the geocoder. onPick(result) is called with {label, lat, lng, area, kind}. */
  function attachSearch(input, list, onPick) {
    function close() { list.hidden = true; list.textContent = ""; }
    var run = debounce(function () {
      var q = input.value.trim();
      if (q.length < 3) { close(); return; }
      call("/api/v1/geo/geocode/?" + qs({ q: q })).then(function (data) {
        list.textContent = "";
        if (!data.results.length) {
          var empty = el("li");
          var msg = el("button", "", data.available ? "No matches. Drop a pin on the map instead." : "Address search is unavailable right now. Drop a pin on the map instead.");
          msg.type = "button"; msg.disabled = true; empty.appendChild(msg); list.appendChild(empty);
        }
        data.results.forEach(function (r) {
          var li = el("li"), b = el("button", "", r.label);
          b.type = "button";
          if (r.area) { b.appendChild(el("span", "geo-sub", r.area)); }
          b.addEventListener("click", function () { close(); onPick(r); });
          li.appendChild(b); list.appendChild(li);
        });
        list.hidden = false;
      }).catch(function () { close(); });
    }, 450);
    input.addEventListener("input", run);
    input.addEventListener("keydown", function (e) { if (e.key === "Escape") { close(); } });
    document.addEventListener("click", function (e) { if (!list.contains(e.target) && e.target !== input) { close(); } });
    return { close: close };
  }

  function initGeocode() {
    $$("[data-geocode]").forEach(function (box) {
      var input = $("[data-geocode-input]", box), list = $("[data-geocode-list]", box);
      var latF = $("input[name=dropoff_lat]", box), lngF = $("input[name=dropoff_lng]", box), geoF = $("input[name=dropoff_geocoded]", box);
      var note = $("[data-geocode-note]", box), mapNode = $("[data-geocode-map]", box);
      var areaSel = box.closest("form") ? box.closest("form").querySelector("select[name=dropoff_area]") : null;
      var map = null, marker = null, origin = "";   // origin: "search" | "pin" | ""

      function say(t) { if (note) { note.textContent = t || ""; } }
      function areaCentre() {
        if (!areaSel) { return null; }
        var o = areaSel.options[areaSel.selectedIndex];
        var la = o && num(o.getAttribute("data-lat")), lo = o && num(o.getAttribute("data-lng"));
        return la !== null && lo !== null ? [la, lo] : null;
      }
      function setPoint(lat, lng, how, label, area) {
        latF.value = lat.toFixed(6); lngF.value = lng.toFixed(6);
        geoF.value = how === "search" ? "true" : "false"; origin = how;
        if (label && !input.value.trim()) { input.value = label; }
        if (area && areaSel) {
          for (var i = 0; i < areaSel.options.length; i++) { if (areaSel.options[i].value === area) { areaSel.selectedIndex = i; break; } }
        }
        say("📍 Drop-off pinned" + (area ? " near " + area : "") + ". Drag the pin if it's a little off.");
        if (marker) { marker.setLatLng([lat, lng]); }
        if (map) { map.setView([lat, lng], Math.max(map.getZoom(), 16)); }
      }
      function clearPoint() { latF.value = lngF.value = ""; geoF.value = "false"; origin = ""; say(""); }
      function reverse(lat, lng) {
        call("/api/v1/geo/reverse/?" + qs({ lat: lat, lng: lng })).then(function (r) {
          if (!input.value.trim() && r.label) { input.value = r.label; }
          say("📍 " + (r.label || "Pinned location") + (r.approximate ? " (approximate)" : ""));
          if (r.area && areaSel) {
            for (var i = 0; i < areaSel.options.length; i++) { if (areaSel.options[i].value === r.area) { areaSel.selectedIndex = i; break; } }
          }
        }).catch(function () { /* the pin is still valid without a label */ });
      }
      function ensureMap() {
        if (map) { return; }
        mapNode.hidden = false;
        var start = (latF.value && [num(latF.value), num(lngF.value)]) || areaCentre();
        map = makeMap(mapNode, start, start ? 16 : 13);
        if (!map) { return; }
        marker = L.marker(start || map.getCenter(), { draggable: true, icon: pin("drop", "🏠") }).addTo(map);
        marker.on("dragend", function () { var p = marker.getLatLng(); setPoint(p.lat, p.lng, "pin"); reverse(p.lat, p.lng); });
        map.on("click", function (e) { marker.setLatLng(e.latlng); setPoint(e.latlng.lat, e.latlng.lng, "pin"); reverse(e.latlng.lat, e.latlng.lng); });
      }

      attachSearch(input, list, function (r) { input.value = r.label; setPoint(r.lat, r.lng, "search", r.label, r.area); });
      input.addEventListener("input", function () { if (origin === "search") { clearPoint(); } });

      var hereBtn = $("[data-geocode-here]", box);
      if (hereBtn) {
        hereBtn.addEventListener("click", function () {
          hereBtn.disabled = true;
          locate().then(function (pos) {
            ensureMap(); setPoint(pos.lat, pos.lng, "pin"); reverse(pos.lat, pos.lng);
          }).catch(fail).then(function () { hereBtn.disabled = false; });
        });
      }
      var pinBtn = $("[data-geocode-pin]", box);
      if (pinBtn) {
        pinBtn.addEventListener("click", function () {
          if (mapNode.hidden) { ensureMap(); reveal(map); pinBtn.textContent = "Hide map"; }
          else { mapNode.hidden = true; pinBtn.textContent = "Pin on map"; }
        });
      }
      if (areaSel) {
        areaSel.addEventListener("change", function () {
          var c = areaCentre();
          if (map && c && !latF.value) { map.setView(c, 14); marker.setLatLng(c); }
        });
      }
    });
  }

  // ------------------------------------------------------------------ trip view (tracking + rider nav) --
  function TripView(panel) {
    this.panel = panel;
    this.mapNode = $("[data-trip-map]", panel);
    this.statusNode = $("[data-trip-status]", panel);
    this.etaNode = $("[data-trip-eta]", panel);
    this.map = null; this.layer = null; this.fitted = null;
  }
  TripView.prototype.draw = function (d) {
    if (!this.map) { this.map = makeMap(this.mapNode, null, 13); if (!this.map) { return; } this.layer = L.layerGroup().addTo(this.map); }
    this.layer.clearLayers();
    var pts = [];
    function add(p, kind, glyph, title) { if (p) { L.marker([p.lat, p.lng], { icon: pin(kind, glyph), title: title }).addTo(this.layer); pts.push([p.lat, p.lng]); } }
    add.call(this, d.pickup, "shop", "🏪", "Pick-up: " + (d.pickup && d.pickup.label || ""));
    add.call(this, d.dropoff, "drop", "🏠", "Drop-off");
    add.call(this, d.rider, "rider", "🏍️", "Rider");
    if (d.route && d.route.geometry && d.route.geometry.length > 1) {
      L.polyline(d.route.geometry, { color: "#2563eb", weight: 4, opacity: 0.75, dashArray: d.route.source === "estimate" ? "6 8" : null }).addTo(this.layer);
      d.route.geometry.forEach(function (g) { pts.push(g); });
    }
    var sig = (d.leg || "") + ":" + (d.job && d.job.status || "");
    if (pts.length && this.fitted !== sig) { this.map.fitBounds(pts, { padding: [30, 30], maxZoom: 16 }); this.fitted = sig; }
    reveal(this.map);
  };
  TripView.prototype.text = function (d, who) {
    var status = d.job ? (d.job.status_label || d.job.status) : "";
    var bits = [];
    if (who === "member") {
      if (d.live && !d.rider) { bits.push("Waiting for your rider's location…"); }
      if (d.rider && d.rider.age_s > 120) { bits.push("Rider's location last updated " + Math.round(d.rider.age_s / 60) + " min ago."); }
      if (d.route && d.route.source === "estimate") { bits.push("ETA is an estimate."); }
    } else if (d.route && d.route.source === "estimate") { bits.push("Estimate (straight-line distance)."); }
    if (d.route) { bits.push(d.route.distance_km + " km on this leg."); }
    if (this.statusNode) { this.statusNode.textContent = (status ? status + ". " : "") + bits.join(" "); }
    if (this.etaNode) {
      if (d.eta_minutes) {
        this.etaNode.textContent = (who === "member" ? "Arriving in about " : "About ") + d.eta_minutes + " min · " + clock(d.eta_at);
      } else if (d.route && d.leg === "trip") {
        this.etaNode.textContent = "Shop to you: about " + d.route.duration_min + " min once a rider is on the way";
      } else { this.etaNode.textContent = ""; }
    }
  };

  function initTracking() {
    $$("[data-track-url]").forEach(function (btn) {
      var panel = document.getElementById(btn.getAttribute("data-track-panel"));
      if (!panel) { return; }
      var view = new TripView(panel), timer = null;
      function load() {
        call(btn.getAttribute("data-track-url")).then(function (d) {
          view.text(d, "member");                      // text first: the ETA must show even if the map fails to draw
          try { view.draw(d); } catch (e) { /* map unavailable: ETA above still stands */ }
          if (!d.live && timer) { clearInterval(timer); timer = null; }
        }).catch(function (e) { if (view.statusNode) { view.statusNode.textContent = e.message; } });
      }
      btn.addEventListener("click", function () {
        var open = panel.hidden;
        panel.hidden = !open;
        btn.textContent = open ? "Hide map" : "Track";
        if (timer) { clearInterval(timer); timer = null; }
        if (open) {
          load();
          timer = setInterval(function () { if (!document.hidden) { load(); } }, 15000);
        }
      });
    });

    // rider: route + ETA for a job
    var navPanel = $("[data-nav-panel]");
    if (navPanel) {
      var nav = new TripView(navPanel), last = null;
      var closeBtn = $("[data-nav-close]", navPanel);
      if (closeBtn) { closeBtn.addEventListener("click", function () { navPanel.hidden = true; document.body.removeAttribute("data-geo-busy"); }); }
      $$("[data-nav-url]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          navPanel.hidden = false;
          document.body.setAttribute("data-geo-busy", "1");   // pause the rider page's 30 s auto-reload while the map is open
          navPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
          var url = btn.getAttribute("data-nav-url");
          function go(pos) {
            var q = pos ? "?" + qs({ lat: pos.lat, lng: pos.lng }) : "";
            call(url + q).then(function (d) { nav.text(d, "rider"); try { nav.draw(d); } catch (e) { /* ETA still shown */ } }).catch(function (e) { if (nav.statusNode) { nav.statusNode.textContent = e.message; } });
          }
          if (window.__riderPos) { go(window.__riderPos); }
          else { locate().then(go).catch(function () { go(null); }); }
        });
      });
    }
  }

  // ------------------------------------------------------------------ rider live sharing --
  function initRiderShare() {
    var box = $("[data-rider-share]");
    if (!box) { return; }
    var status = $("[data-rider-share-status]"), watchId = null, lastSent = 0, sentOnce = false;
    function say(t) { if (status) { status.textContent = t; } }
    function stop() {
      if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
      store("sc_rider_share", null); say("Not sharing. Customers can't see your position.");
    }
    function start() {
      if (!navigator.geolocation) { box.checked = false; say("This browser can't share its location."); return; }
      store("sc_rider_share", "1"); say("Waiting for GPS…");
      watchId = navigator.geolocation.watchPosition(function (p) {
        window.__riderPos = { lat: p.coords.latitude, lng: p.coords.longitude };
        var now = Date.now();
        if (now - lastSent < 15000) { return; }
        lastSent = now;
        call("/api/v1/rider/location/", "POST", { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }).then(function (r) {
          sentOnce = true;
          say(r.tracking ? "Sharing live with your customer. Keep this page open." : "GPS ready. Sharing starts when you accept a delivery. Keep this page open.");
        }).catch(function (e) { say(e.message); });
      }, function (e) {
        box.checked = false; stop();
        say(e && e.code === 1 ? "Location permission denied." : "Couldn't read your GPS.");
      }, { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
    }
    box.addEventListener("change", function () { if (box.checked) { start(); } else { stop(); } });
    if (recall("sc_rider_share") === "1") { box.checked = true; start(); }
    window.addEventListener("pagehide", function () { if (watchId !== null) { navigator.geolocation.clearWatch(watchId); } });
  }

  // ------------------------------------------------------------------ shop pin (merchant) --
  function initShopPin() {
    $$("[data-shop-pin]").forEach(function (box) {
      var mapNode = $("[data-shop-map]", box), save = $("[data-shop-save]", box), note = $("[data-shop-note]", box);
      var input = $("[data-shop-search]", box), list = $("[data-shop-list]", box), here = $("[data-shop-here]", box);
      var lat = num(box.getAttribute("data-lat")), lng = num(box.getAttribute("data-lng"));
      var aLat = num(box.getAttribute("data-area-lat")), aLng = num(box.getAttribute("data-area-lng"));
      var start = lat !== null ? [lat, lng] : (aLat !== null ? [aLat, aLng] : null);
      var map = makeMap(mapNode, start, lat !== null ? 17 : 14);
      if (!map) { return; }
      var marker = L.marker(start || map.getCenter(), { draggable: true, icon: pin("shop", "🏪") }).addTo(map);
      var dirty = lat === null, address = "";
      function say(t) { note.textContent = t; }
      function moved(p) { lat = p.lat; lng = p.lng; dirty = true; save.disabled = false; say("Pin moved. Press “Save shop location” to keep it."); }
      marker.on("dragend", function () { moved(marker.getLatLng()); });
      map.on("click", function (e) { marker.setLatLng(e.latlng); moved(e.latlng); });
      save.disabled = !dirty;
      say(lat === null ? "Not pinned yet. Customers see your area's centre until you drop the pin on your shop." : "Your shop is pinned. Drag the pin to adjust it.");
      attachSearch(input, list, function (r) { input.value = r.label; address = r.label; marker.setLatLng([r.lat, r.lng]); map.setView([r.lat, r.lng], 17); moved({ lat: r.lat, lng: r.lng }); });
      if (here) {
        here.addEventListener("click", function () {
          here.disabled = true;
          locate().then(function (pos) { marker.setLatLng([pos.lat, pos.lng]); map.setView([pos.lat, pos.lng], 17); moved({ lat: pos.lat, lng: pos.lng }); })
            .catch(fail).then(function () { here.disabled = false; });
        });
      }
      save.addEventListener("click", function () {
        if (lat === null) { toast("Drop the pin on your shop first."); return; }
        save.disabled = true;
        call(box.getAttribute("data-save-url"), "POST", { lat: lat, lng: lng, address: address }).then(function () {
          dirty = false; say("Saved. Nearby members will now see accurate distances to your shop.");
        }).catch(function (e) { save.disabled = false; fail(e); });
      });
      var wrap = box.closest("details");
      if (wrap) { wrap.addEventListener("toggle", function () { reveal(map); }); }
      reveal(map);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!API || !cfg) { return; }
    initDeals(); initSettings(); initGeocode(); initTracking(); initRiderShare(); initShopPin();
  });
})();
