self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch (_) { payload = {}; }
  event.waitUntil(self.registration.showNotification(payload.title || 'Jarvis bildirimi', {
    body: payload.body || 'Yeni bir bildirim var.',
    icon: '/iphone-icon.png',
    tag: payload.tag || 'jarvis',
    data: { url: '/mobile/index.html?tab=approvals' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/mobile/index.html?tab=approvals'));
});
