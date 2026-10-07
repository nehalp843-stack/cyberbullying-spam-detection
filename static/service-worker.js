const CACHE_NAME = "safe-signal-v2";
const APP_SHELL = [
    "/static/offline.html",
    "/static/manifest.webmanifest",
    "/static/icons/app-icon.svg"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => Promise.all(
                cacheNames
                    .filter((cacheName) => cacheName.startsWith("safe-signal-") && cacheName !== CACHE_NAME)
                    .map((cacheName) => caches.delete(cacheName))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== "GET" || url.origin !== self.location.origin) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith((async () => {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 20000);
            try {
                const response = await fetch(request, { signal: controller.signal });
                if (response.ok) {
                    return response;
                }
            } catch (error) {
                console.warn("App server is unavailable; showing the offline page.", error);
            } finally {
                clearTimeout(timeoutId);
            }
            return await caches.match("/static/offline.html")
                || new Response(
                    "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">" +
                    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
                    "<title>Safe Signal is temporarily unavailable</title>" +
                    "<body style=\"font:16px system-ui;max-width:36rem;margin:15vh auto;padding:1.5rem;" +
                    "color:#17233b;background:#f2f5fb\"><h1>Safe Signal is temporarily unavailable</h1>" +
                    "<p>The server may be restarting or your connection may be offline.</p>" +
                    "<button onclick=\"location.reload()\">Try again</button></body></html>",
                    { headers: { "Content-Type": "text/html; charset=utf-8" } }
                );
        })());
        return;
    }

    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then((cached) => cached || fetch(request).then((response) => {
                if (response.ok) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                }
                return response;
            }))
        );
    }
});
