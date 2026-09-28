import { proxyRequest } from "../proxy.js";

export async function onRequest({ request }) {
  return proxyRequest(request);
}

export default onRequest;
