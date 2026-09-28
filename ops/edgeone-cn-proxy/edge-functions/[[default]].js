const ORIGIN = "https://medicalchannelai.vercel.app";

async function proxyRequest(request) {
  try {
    const incomingUrl = new URL(request.url);

    if (incomingUrl.pathname === "/__mcai_edge_probe") {
      return new Response("MCAI Edge proxy probe OK", {
        status: 200,
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "no-store",
          "x-mcai-edge-proxy": "probe",
        },
      });
    }

    const pathname = incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname;
    const targetUrl = new URL(pathname, ORIGIN);

    incomingUrl.searchParams.forEach((value, key) => {
      if (key !== "eo_token" && key !== "eo_time") {
        targetUrl.searchParams.append(key, value);
      }
    });

    const requestHeaders = {};
    request.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (
        lower !== "host" &&
        lower !== "connection" &&
        lower !== "content-length" &&
        lower !== "accept-encoding"
      ) {
        requestHeaders[key] = value;
      }
    });
    requestHeaders.origin = ORIGIN;
    requestHeaders.referer = ORIGIN + "/";
    requestHeaders["accept-encoding"] = "identity";

    const init = {
      method: request.method,
      headers: requestHeaders,
      redirect: "manual",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.arrayBuffer();
    }

    const originResponse = await fetch(targetUrl.toString(), init);

    const responseHeaders = {};
    originResponse.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (
        lower !== "content-length" &&
        lower !== "content-encoding" &&
        lower !== "transfer-encoding"
      ) {
        responseHeaders[key] = value;
      }
    });

    const location = originResponse.headers.get("location");
    if (location) {
      try {
        const redirectUrl = new URL(location, targetUrl);
        if (redirectUrl.origin === ORIGIN) {
          redirectUrl.protocol = incomingUrl.protocol;
          redirectUrl.host = incomingUrl.host;
          responseHeaders.location = redirectUrl.toString();
        }
      } catch {
        // Keep the original Location if it cannot be parsed.
      }
    }

    responseHeaders["x-mcai-edge-proxy"] = "edgeone-makers-v8";

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

export default function onRequest(context) {
  return proxyRequest(context.request);
}
