/* Service worker do Hub Capture — só Web Push (§63).
 *
 * Não faz cache de página nem intercepta fetch: o app segue 100% online, e um
 * SW de cache mal invalidado é o jeito mais rápido de servir UI velha depois
 * de um deploy. Ele existe para duas coisas: mostrar a notificação que o
 * servidor mandou e, no clique, levar o gestor à tela certa.
 */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let dados = {};
  try {
    dados = event.data ? event.data.json() : {};
  } catch {
    dados = { body: event.data ? event.data.text() : "" };
  }
  const titulo = dados.title || "Hub Capture";
  event.waitUntil(
    self.registration.showNotification(titulo, {
      body: dados.body || "Há novidades nas propostas que você acompanha.",
      tag: dados.tag || "hub",
      // mesma tag = substitui a anterior; renotify faz vibrar de novo
      renotify: true,
      icon: "/icon.svg",
      badge: "/icon.svg",
      data: { url: dados.url || "/panel/alerts" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const destino = new URL(
    (event.notification.data && event.notification.data.url) || "/panel/alerts",
    self.location.origin,
  ).href;
  event.waitUntil(
    (async () => {
      const abertas = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      // reaproveita uma aba do app já aberta em vez de empilhar abas
      for (const c of abertas) {
        if (c.url.startsWith(self.location.origin) && "focus" in c) {
          await c.focus();
          if ("navigate" in c) await c.navigate(destino);
          return;
        }
      }
      await self.clients.openWindow(destino);
    })(),
  );
});
