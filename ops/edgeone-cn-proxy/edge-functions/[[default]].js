const ORIGIN = "https://medicalchannelai.vercel.app";

async function proxyRequest(request) {
  try {
    const incomingUrl = new URL(request.url);
    const pathname = incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname;

    const targetUrl = new URL(pathname, ORIGIN);
    for (const [key, value] of incomingUrl.searchParams) {
      if (key !== "eo_token" && key !== "eo_time") {
        targetUrl.searchParams.append(key, value);
      }
    }

    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("connection");
    headers.delete("content-length");
    headers.set("origin", ORIGIN);
    headers.set("referer", ORIGIN + "/");

    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.arrayBuffer();
    }

    const originResponse = await fetch(targetUrl.toString(), init);
    const responseHeaders = new Headers(originResponse.headers);

    const location = responseHeaders.get("location");
    if (location) {
      const redirectUrl = new URL(location, targetUrl);
      if (redirectUrl.origin === ORIGIN) {
        redirectUrl.protocol = incomingUrl.protocol;
        redirectUrl.host = incomingUrl.host;
        responseHeaders.set("location", redirectUrl.toString());
      }
    }

    const allowOrigin = responseHeaders.get("access-control-allow-origin");
    if (allowOrigin === ORIGIN) {
      responseHeaders.set("access-control-allow-origin", incomingUrl.origin);
    }

    responseHeaders.set("x-mcai-edge-proxy", "edgeone-makers");

    return new Response(originResponse.body, {
      status: originResponse.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    return new Response("MCAI Edge proxy runtime error: " + message, {
      status: 502,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store",
        "x-mcai-edge-proxy": "runtime-error",
      },
    });
  }
}

export default async function onRequest(context) {
  return proxyRequest(context.request);
}
