// Canonical host for the blog is https://blog.agendaburn.com.
// The Cloudflare Pages default hostname must 301 there, and unknown paths
// must be real 404s. Pages' _redirects file cannot match on hostname, and a
// project-level SPA fallback would keep serving index.html with status 200.

const ARTICLES = [
  "/37-billion-wasted-on-meetings-is-your-company-guilty",
  "/async-first-manifesto-replace-71-of-meetings-with-docs",
  "/how-much-does-a-meeting-cost-your-company",
  "/meeting-cost-calculator-how-much-is-your-stand-up",
  "/why-most-meetings-are-useless-and-cost-you-millions",
];

const FILES = new Set([
  "/",
  "/robots.txt",
  "/sitemap.xml",
  "/llms.txt",
  "/404.html",
]);

export async function onRequest(context) {
  const url = new URL(context.request.url);

  if (url.hostname === "agendaburn-blog.pages.dev") {
    url.hostname = "blog.agendaburn.com";
    url.protocol = "https:";
    return Response.redirect(url.toString(), 301);
  }

  const path = url.pathname;
  const bare = path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;

  if (path === "/index.html" || (ARTICLES.includes(bare) && path === bare)) {
    url.pathname = path === "/index.html" ? "/" : bare + "/";
    return Response.redirect(url.toString(), 301);
  }

  const allowed = FILES.has(path) || ARTICLES.some((article) => path === article + "/");
  if (!allowed) {
    let html = "<!DOCTYPE html><title>Page not found</title><p>Not found.</p>";
    try {
      const asset = await context.env.ASSETS.fetch(new URL("/404.html", url.origin));
      if (asset.ok) html = await asset.text();
    } catch (_err) {
      /* fall back to the short document above */
    }
    return new Response(html, {
      status: 404,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "x-robots-tag": "noindex",
        "cache-control": "public, max-age=0, must-revalidate",
      },
    });
  }

  return context.next();
}
