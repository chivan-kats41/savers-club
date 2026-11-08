/* 1K Saver Club service worker: shows Web Push notifications and opens the right page when one is tapped.
   It does no caching and intercepts no requests. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  var title = data.title || "1K Saver Club";
  var options = { body: data.body || "", data: { url: data.url || "/" } };
  if (data.tag) { options.tag = data.tag; }
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var target = "/";
  try {
    var u = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin);
    if (u.origin === self.location.origin) { target = u.pathname + u.search + u.hash; }   // same-origin links only
  } catch (e) { /* keep "/" */ }
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if ("focus" in list[i] && "navigate" in list[i]) { return list[i].navigate(target).then(function (c) { return c && c.focus(); }); }
    }
    return self.clients.openWindow(target);
  }));
});
