const ORIGIN = "https://medicalchannelai.vercel.app";

export async function proxyRequest(request) {
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
    // A pathname beginning with // is a network-path reference to URL(base).
    // Assign it as a path on a fixed URL instead, and reject ambiguous inputs
    // before forwarding any cookie, authorization header or request body.
    let decodedPath;
    try {
      decodedPath = decodeURIComponent(pathname);
    } catch {
      return new Response("Invalid proxy path", { status: 400 });
    }
    if (/^\/[\/\\]/.test(decodedPath) || decodedPath.includes("\\")) {
      return new Response("Invalid proxy path", { status: 400 });
    }
    const targetUrl = new URL(ORIGIN);
    targetUrl.pathname = pathname;

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
    requestHeaders["accept-encoding"] = "identity";

    const init = {
      method: request.method,
      headers: requestHeaders,
      redirect: "manual",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.arrayBuffer();
    }

    if (targetUrl.origin !== ORIGIN) throw new Error("UNTRUSTED_PROXY_ORIGIN");
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
    return new Response("MCAI Edge proxy upstream unavailable", {
      status: 502,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store",
        "x-mcai-edge-proxy": "runtime-error",
      },
    });
  }
}

