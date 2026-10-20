// Browser-side tests for hub/static/hub/js/geo.js, run in a simulated browser (jsdom).
//   cd /tmp && npm i jsdom && NODE_PATH=/tmp/node_modules node /path/to/hub/static_tests/geo.test.js
const { JSDOM } = require("jsdom");
const fs = require("fs"), path = require("path");
const SRC = fs.readFileSync(path.join(__dirname, "../static/hub/js/geo.js"), "utf8");
let failed = 0;
const ok = (c, m) => { if (!c) { failed++; console.log("  FAIL:", m); } else console.log("  ok:  ", m); };
const tick = (ms = 20) => new Promise(r => setTimeout(r, ms));

function page({ html, secure = true, geoloc, perm = "prompt", posts }) {
  const dom = new JSDOM(`<!doctype html><body>${html}</body>`, { runScripts: "outside-only", url: secure ? "https://x.test/member/" : "http://x.test/member/", pretendToBeVisual: true });
  const w = dom.window;
  Object.defineProperty(w, "isSecureContext", { value: secure });
  if (geoloc) Object.defineProperty(w.navigator, "geolocation", { value: geoloc, configurable: true });
  Object.defineProperty(w.navigator, "permissions", { value: { query: async () => ({ state: perm }) }, configurable: true });
  const toasts = []; let reloaded = 0;
  w.SaverAPI = { api: async (url, opts) => { posts.push({ url, body: opts.body }); return { data: { changed: true, ...(opts.__resp || {}) } }; }, toast: (m, k) => toasts.push({ m, k }) };
  w.eval(SRC);
  w.SaverGeo.hooks.reload = () => { reloaded++; };
  // jsdom fires DOMContentLoaded by itself right after construction (as a real browser does)
  return { w, toasts, reloads: () => reloaded };
}
const okGeo = (lat, lng, acc = 20) => ({ getCurrentPosition: (s) => s({ coords: { latitude: lat, longitude: lng, accuracy: acc } }), watchPosition: (s) => { s({ coords: { latitude: lat, longitude: lng, accuracy: acc } }); return 1; } });
const errGeo = (code) => ({ getCurrentPosition: (s, e) => e({ code, message: "x" }), watchPosition: (s, e) => { e({ code }); return 1; } });

(async () => {
  console.log("1. pressing 'Share my location' sends the position and reloads");
  let posts = [];
  let p = page({ html: '<button data-geo-locate data-geo-role="member" data-geo-reload>Share</button>', geoloc: okGeo(0.3291, 32.6492), posts });
  p.w.document.querySelector("button").click(); await tick(500);
  ok(posts.length === 1 && posts[0].url === "/api/v1/geo/location/", "POST /api/v1/geo/location/");
  ok(posts[0].body.role === "member" && posts[0].body.lat === 0.3291 && posts[0].body.lng === 32.6492 && posts[0].body.accuracy === 20, "sends role, lat, lng, accuracy");
  ok(p.reloads() === 1, "page reloads so results are recomputed");

  console.log("2. permission denied -> clear message, no request, button usable again");
  posts = [];
  p = page({ html: '<button data-geo-locate data-geo-role="member">Share</button>', geoloc: errGeo(1), posts });
  const b = p.w.document.querySelector("button"); b.click(); await tick();
  ok(posts.length === 0, "nothing sent to the server");
  ok(p.toasts.length === 1 && /blocked/i.test(p.toasts[0].m) && /area/i.test(p.toasts[0].m) && p.toasts[0].k === "error", "explains how to unblock and offers the area fallback");
  ok(!b.disabled && b.textContent === "Share", "button restored");

  console.log("3. insecure (http) page -> explains, does not call the browser API");
  posts = []; let called = 0;
  p = page({ html: '<button data-geo-locate>Share</button>', secure: false, geoloc: { getCurrentPosition() { called++; } }, posts });
  p.w.document.querySelector("button").click(); await tick();
  ok(called === 0 && posts.length === 0, "no geolocation call, no request");
  ok(/secure connection/i.test(p.toasts[0].m), "tells the person why");

  console.log("4. position unavailable / timeout messages");
  for (const [code, re] of [[2, /couldn't work out/i], [3, /too long/i]]) {
    posts = []; p = page({ html: '<button data-geo-locate>Share</button>', geoloc: errGeo(code), posts });
    p.w.document.querySelector("button").click(); await tick();
    ok(re.test(p.toasts[0].m), `code ${code}: ${p.toasts[0].m.slice(0, 40)}...`);
  }

  console.log("5. silent refresh only when permission is already granted and the stored point is stale");
  posts = []; p = page({ html: '<div data-geo-auto="member" data-geo-age="900"></div>', geoloc: okGeo(0.33, 32.65), perm: "granted", posts }); await tick(60);
  ok(posts.length === 1, "granted + stale -> refreshes without a prompt");
  posts = []; p = page({ html: '<div data-geo-auto="member" data-geo-age="30"></div>', geoloc: okGeo(0.33, 32.65), perm: "granted", posts }); await tick(60);
  ok(posts.length === 0, "fresh point -> does nothing");
  posts = []; p = page({ html: '<div data-geo-auto="member" data-geo-age="900"></div>', geoloc: okGeo(0.33, 32.65), perm: "prompt", posts }); await tick(60);
  ok(posts.length === 0, "permission not yet granted -> never pops a surprise prompt");
  posts = []; p = page({ html: '<div data-geo-auto="member" data-geo-age="900"></div>', geoloc: okGeo(0.33, 32.65), perm: "granted", posts }); await tick(60);
  ok(p.reloads() === 1, "moved since last time -> reloads once");
  posts = []; p = page({ html: '<div data-geo-auto="member" data-geo-age="900"></div>', geoloc: okGeo(0.33, 32.65), perm: "granted", posts });
  p.w.sessionStorage.setItem("geoReloadAt", String(Date.now())); await tick(60);
  ok(p.reloads() === 0, "just reloaded a moment ago -> will not reload-loop");

  console.log("6. rider live sharing is throttled to once per 30 s");
  posts = []; let cb;
  const watcher = { getCurrentPosition() {}, watchPosition: (s) => { cb = s; return 1; } };
  p = page({ html: '<div id="geo-rider-status"></div><section data-geo-watch="rider" data-geo-state="live" data-geo-prompt></section>', geoloc: watcher, perm: "granted", posts }); await tick(30);
  const fix = { coords: { latitude: 0.33, longitude: 32.65, accuracy: 15 } };
  cb(fix); await tick(); cb(fix); cb(fix); await tick();
  ok(posts.length === 1 && posts[0].body.role === "rider", "three fixes in a row -> one request");
  ok(/live location/i.test(p.w.document.getElementById("geo-rider-status").textContent), "status line updates");

  console.log("7. rider with permission denied sees the instruction, nothing is sent");
  posts = []; p = page({ html: '<div id="geo-rider-status"></div><section data-geo-watch="rider"></section>', geoloc: okGeo(1, 1), perm: "denied", posts }); await tick(30);
  ok(posts.length === 0 && /blocked/i.test(p.w.document.getElementById("geo-rider-status").textContent), "explains how to allow it");

  console.log(failed ? `\n${failed} FAILED` : "\nall browser tests passed");
  process.exit(failed ? 1 : 0);
})();
