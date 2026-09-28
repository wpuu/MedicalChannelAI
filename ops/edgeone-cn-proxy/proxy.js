const ORIGIN = "https://medicalchannelai.vercel.app";

export async function proxyRequest(request) {
  const incomingUrl = new URL(request.url);
  const pathname = incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname;
  const targetUrl = new URL(pathname + incomingUrl.search, ORIGIN);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.delete("host");
  requestHeaders.delete("connection");
  requestHeaders.delete("content-length");
  requestHeaders.set("x-forwarded-host", incomingUrl.host);
  requestHeaders.set("x-forwarded-proto", "https");
  requestHeaders.set("x-mcai-edge-proxy", "edgeone-pages");

  const init = {
    method: request.method,
    headers: requestHeaders,
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  const originResponse = await fetch(targetUrl.toString(), init);
  const responseHeaders = new Headers(originResponse.headers);

  const location = responseHeaders.get("location");
  if (location) {
    try {
      const redirectUrl = new URL(location, targetUrl);
      if (redirectUrl.origin === ORIGIN) {
        redirectUrl.protocol = incomingUrl.protocol;
        redirectUrl.host = incomingUrl.host;
        responseHeaders.set("location", redirectUrl.toString());
      }
    } catch {
      // Keep malformed/relative Location untouched.
    }
  }

  const allowOrigin = responseHeaders.get("access-control-allow-origin");
  if (allowOrigin === ORIGIN) {
    responseHeaders.set("access-control-allow-origin", incomingUrl.origin);
  }

  responseHeaders.set("x-mcai-edge-proxy", "edgeone-pages");

  return new Response(originResponse.body, {
    status: originResponse.status,
    statusText: originResponse.statusText,
    headers: responseHeaders,
  });
}
