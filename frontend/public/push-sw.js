/* Web Push handlers, imported by the generated service worker.
 * The payload is produced by the backend's apps/notifications/push.py and
 * carries only the notification's own title, message, click path and tag.
 */
self.addEventListener("push", function (event) {
  var payload = {}
  try {
    payload = event.data ? event.data.json() : {}
  } catch (error) {
    payload = {
      title: "AEGIS — HIS CARE CHRISTIAN INSTITUTE",
      body: event.data ? event.data.text() : "",
    }
  }
  var title = payload.title || "AEGIS — HIS CARE CHRISTIAN INSTITUTE"
  var options = {
    body: payload.body || "",
    tag: payload.tag || "aegis",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: { url: payload.url || "/app/notifications" },
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener("notificationclick", function (event) {
  var notification = event.notification
  var url = (notification.data && notification.data.url) || "/app/notifications"
  notification.close()

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then(function (windowClients) {
        for (var index = 0; index < windowClients.length; index += 1) {
          var client = windowClients[index]
          if ("focus" in client) {
            var focused = client.focus()
            if (client.navigate) {
              client.navigate(url).catch(function () {})
            }
            return focused
          }
        }
        return self.clients.openWindow(url)
      })
  )
})
