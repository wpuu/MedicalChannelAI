import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { CheckCircle2, Info, X } from 'lucide-react'

interface ToastItem {
  id: string
  message: string
  tone: 'info' | 'success'
}

interface ToastContextValue {
  toast: (message: string, tone?: ToastItem['tone']) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const toast = useCallback((message: string, tone: ToastItem['tone'] = 'info') => {
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    setItems((prev) => [...prev, { id, message, tone }])
    window.setTimeout(() => {
      setItems((prev) => prev.filter((item) => item.id !== id))
    }, 3200)
  }, [])

  const value = useMemo(() => ({ toast }), [toast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[80] flex justify-center px-4">
        <div className="flex w-full max-w-md flex-col gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="pointer-events-auto animate-toast-in flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-3 shadow-lg"
            >
              {item.tone === 'success' ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" />
              ) : (
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
              )}
              <p className="flex-1 text-[13px] leading-5 text-slate-700">{item.message}</p>
              <button
                type="button"
                className="shrink-0 text-slate-400"
                onClick={() => setItems((prev) => prev.filter((x) => x.id !== item.id))}
                aria-label="关闭提示"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return ctx
}
