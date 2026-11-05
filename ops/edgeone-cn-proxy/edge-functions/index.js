import { proxyRequest } from "../proxy.js";

export default function onRequest(context) {
  return proxyRequest(context.request);
}
