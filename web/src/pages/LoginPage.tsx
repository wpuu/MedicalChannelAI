import { FormEvent, useEffect, useState } from 'react'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { isApiMode, redeemPilotInvite } from '@/services/apiConfig'

export function LoginPage() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isApiMode) return
    const fragment = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash
    const value = new URLSearchParams(fragment).get('code')?.trim()
    if (!value) return
    setCode(value)
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
  }, [])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalized = code.trim()
    if (normalized.length < 32) {
      setError('邀请码格式不正确。')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await redeemPilotInvite(normalized)
      setCode('')
      navigate('/profile', { replace: true })
    } catch (cause) {
      if (cause instanceof Error && cause.message === 'INVITE_INVALID_OR_EXPIRED') {
        setError('邀请码无效、已使用或已过期，请联系管理员重新获取。')
      } else {
        setError('登录暂时失败，请稍后重试。')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (!isApiMode) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f3f5f7] px-4">
        <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-lg font-semibold text-slate-900">医疗商机助手</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            当前为本地演示模式，不需要登录，也不会连接真实客户数据。
          </p>
          <button
            type="button"
            onClick={() => navigate('/today', { replace: true })}
            className="mt-5 w-full rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-teal-800"
          >
            进入演示
          </button>
        </section>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f3f5f7] px-4 py-10">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-700 text-white">
            <KeyRound className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-900">医疗商机助手</h1>
            <p className="text-xs text-slate-500">天津 Pilot · 一次性邀请登录</p>
          </div>
        </div>

        <form className="mt-6" onSubmit={submit}>
          <label htmlFor="invite-code" className="text-sm font-medium text-slate-700">
            邀请码
          </label>
          <input
            id="invite-code"
            type="password"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            autoComplete="one-time-code"
            spellCheck={false}
            placeholder="粘贴管理员提供的一次性邀请码"
            className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
          />
          {error ? (
            <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={submitting}
            className="mt-4 w-full rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? '正在验证…' : '进入系统'}
          </button>
        </form>

        <div className="mt-5 flex items-start gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <p className="text-xs leading-5 text-slate-500">
            邀请码只能使用一次。首次登录先填写医院关系、产品能力和合作资源，保存后系统立即按你的真实资料筛选今日商机，并让需要判断的 Top 5 进入受控 Agnes 分析。
          </p>
        </div>
      </section>
    </main>
  )
}
