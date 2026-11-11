/* Layer 6: W3C Web Push Service Worker (Collect-Only Safe Foundation) */
self.addEventListener("install", function(event) {
  self.skipWaiting();
});

self.addEventListener("activate", function(event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function(event) {
  if (!event.data) return;
  let data = {};
  try {
    data = event.data.json();
  } catch (e) {
    data = { title: "Latest Update", body: event.data.text() || "" };
  }
  const title = data.title || "Financial & Telecom Update";
  const options = {
    body: data.body || data.message || "New guide published.",
    icon: data.icon || "/favicon.ico",
    data: { url: data.url || "/" }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function(event) {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.openWindow(targetUrl));
});
