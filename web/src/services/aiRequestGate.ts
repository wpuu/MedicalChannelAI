type Listener = () => void

let busy = false
const listeners = new Set<Listener>()

function emit(): void {
  for (const listener of listeners) listener()
}

export function getAiRequestBusySnapshot(): boolean {
  return busy
}

export function subscribeAiRequestBusy(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function beginAiRequest(): boolean {
  if (busy) return false
  busy = true
  emit()
  return true
}

export function endAiRequest(): void {
  if (!busy) return
  busy = false
  emit()
}
