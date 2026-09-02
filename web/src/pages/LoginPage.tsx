import { FormEvent, useEffect, useState } from 'react'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  isApiMode,
  loginPilotAccount,
  registerPilotAccount,
} from '@/services/apiConfig'

type Mode = 'login' | 'register'

function authMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : ''
  switch (code) {
    case 'INVALID_CREDENTIALS':
      return '账号或密码不正确。'
    case 'INVITE_INVALID_OR_EXPIRED':
      return '邀请码无效、已使用或已过期，请联系管理员重新获取。'
    case 'USERNAME_TAKEN':
      return '这个账号名已经被使用，请换一个。'
    case 'USERNAME_INVALID':
      return '账号名需为 4～32 位英文、数字、点、下划线或短横线。'
    case 'PASSWORD_INVALID':
      return '密码需为 10～128 位。'
    case 'PRIVATE_DATABASE_NOT_CONFIGURED':
      return '试用账号系统尚未完成数据库配置，请联系管理员。'
    default:
      return '操作暂时失败，请检查网络后重试。'
  }
}

export function LoginPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('login')
  const [inviteCode, setInviteCode] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isApiMode) return
    const fragment = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash
    const value = new URLSearchParams(fragment).get('code')?.trim()
    if (!value) return
    setInviteCode(value)
    setMode('register')
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
  }, [])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedUsername = username.trim()
    setError(null)

    if (!/^[A-Za-z0-9._-]{4,32}$/.test(normalizedUsername)) {
      setError('账号名需为 4～32 位英文、数字、点、下划线或短横线。')
      return
    }
    if (password.length < 10 || password.length > 128) {
      setError('密码需为 10～128 位。')
      return
    }
    if (mode === 'register') {
      if (inviteCode.trim().length < 24) {
        setError('邀请码格式不正确。')
        return
      }
      if (password !== confirmPassword) {
        setError('两次输入的密码不一致。')
        return
      }
    }

    setSubmitting(true)
    try {
      if (mode === 'register') {
        await registerPilotAccount({
          inviteCode: inviteCode.trim(),
          username: normalizedUsername,
          password,
        })
      } else {
        await loginPilotAccount({ username: normalizedUsername, password })
      }
      setInviteCode('')
      setPassword('')
      setConfirmPassword('')
      navigate('/today', { replace: true })
    } catch (cause) {
      setError(authMessage(cause))
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
            当前为本地演示模式，不需要登录，也不会连接真实客户账号。
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
            <p className="text-xs text-slate-500">天津 Pilot · 私有账号</p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 rounded-xl bg-slate-100 p-1">
          {(['login', 'register'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setMode(value)
                setError(null)
              }}
              className={`rounded-lg px-3 py-2 text-sm font-medium ${
                mode === value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'
              }`}
            >
              {value === 'login' ? '已有账号' : '邀请码注册'}
            </button>
          ))}
        </div>

        <form className="mt-5 space-y-4" onSubmit={submit}>
          {mode === 'register' ? (
            <label className="block text-sm font-medium text-slate-700">
              邀请码
              <input
                type="password"
                value={inviteCode}
                onChange={(event) => setInviteCode(event.target.value)}
                autoComplete="one-time-code"
                spellCheck={false}
                placeholder="粘贴管理员提供的一次性邀请码"
                className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              />
            </label>
          ) : null}

          <label className="block text-sm font-medium text-slate-700">
            账号名
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              spellCheck={false}
              placeholder="4～32 位英文、数字或 . _ -"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
            />
          </label>

          <label className="block text-sm font-medium text-slate-700">
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              placeholder="至少 10 位"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
            />
          </label>

          {mode === 'register' ? (
            <label className="block text-sm font-medium text-slate-700">
              再次输入密码
              <input
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                autoComplete="new-password"
                className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
              />
            </label>
          ) : null}

          {error ? (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting
              ? mode === 'register' ? '正在创建账号…' : '正在登录…'
              : mode === 'register' ? '创建账号并进入' : '登录'}
          </button>
        </form>

        <div className="mt-5 flex items-start gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <p className="text-xs leading-5 text-slate-500">
            注册默认不要求手机号、邮箱或真实姓名。服务端只保存账号名和密码的加盐强哈希，不保存明文密码；登录后浏览器只持有 HttpOnly 会话 Cookie。你在公开试用阶段已保存在本机的医院关系、产品能力等数据，不会因注册而自动上传。
          </p>
        </div>
      </section>
    </main>
  )
}
