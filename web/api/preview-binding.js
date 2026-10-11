import postgres from 'postgres'
import { checkPreviewBinding } from './_previewBindingCheck.js'

export default async function handler(request, response) {
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store, max-age=0')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  if (request.method !== 'GET') response.setHeader('Allow', 'GET')
  const result = await checkPreviewBinding(request.method, process.env, postgres)
  return response.status(result.status).json(result.body)
}
