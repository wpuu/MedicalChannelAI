import { useRef, useState } from 'react'

export function useOutcomeSave<Reason>(
  onConfirm: (reason: Reason) => boolean | Promise<boolean>,
  onClose: () => void,
) {
  const pending = useRef(false)
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)

  const close = () => {
    if (pending.current) return
    setFailed(false)
    onClose()
  }

  const confirm = async (reason: Reason) => {
    if (pending.current) return
    pending.current = true
    setSaving(true)
    setFailed(false)
    try {
      if (await onConfirm(reason)) onClose()
      else setFailed(true)
    } catch {
      setFailed(true)
    } finally {
      pending.current = false
      setSaving(false)
    }
  }

  return { saving, failed, close, confirm }
}
