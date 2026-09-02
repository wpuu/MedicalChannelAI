import rootDiscoveryHandler from './_discoverRoot.js'
import continuationDiscoveryHandler from './_discoverContinuation.js'

export const config = { maxDuration: 30 }

function routeValue(request) {
  const value = request.query?.route
  return Array.isArray(value) ? value[0] : typeof value === 'string' ? value : null
}

export default async function handler(request, response) {
  if (routeValue(request) === 'continuation') {
    return continuationDiscoveryHandler(request, response)
  }
  return rootDiscoveryHandler(request, response)
}
