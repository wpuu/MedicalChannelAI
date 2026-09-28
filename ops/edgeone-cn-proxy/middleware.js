const ORIGIN = "https://medicalchannelai.vercel.app";

export function middleware(context) {
  const { request, rewrite } = context;
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(incomingUrl.pathname === "/" ? "/today" : incomingUrl.pathname, ORIGIN);

  for (const [key, value] of incomingUrl.searchParams) {
    if (key !== "eo_token" && key !== "eo_time") {
      targetUrl.searchParams.append(key, value);
    }
  }

  return rewrite(targetUrl.toString());
}

export const config = {
  matcher: "/:path*",
};
