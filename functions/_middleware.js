export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  const path = url.pathname;

  // Preserve trailing slash for canonical directory index (/blog/, /article/)
  // Strip trailing slash otherwise
  const isDirRoot = path === "/blog/" || path === "/article/";
  if (!isDirRoot && path.length > 1 && path.endsWith("/")) {
    url.pathname = path.replace(/\/+$/, "");
    return Response.redirect(url.toString(), 301);
  }
  return next();
}
