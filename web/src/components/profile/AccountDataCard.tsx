import { useState } from 'react'
import { Download, Trash2 } from 'lucide-react'
import {
  deletePilotAccount,
  downloadAccountExport,
  exportPilotAccountData,
} from '@/services/accountApi'

function accountErrorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : ''
  if (code === 'PASSWORD_CONFIRMATION_FAILED') return '当前密码不正确。'
  if (code === 'AUTH_REQUIRED') return '登录已失效，请重新登录。'
  if (code === 'PRIVATE_DATABASE_NOT_CONFIGURED') return '账号数据库尚未配置。'
  return '操作失败，请稍后重试。'
}

export function AccountDataCard() {
  const [exporting, setExporting] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const exportData = async () => {
    setExporting(true)
    setMessage(null)
    try {
      const payload = await exportPilotAccountData()
      downloadAccountExport(payload)
      setMessage('账号数据已导出为 JSON 文件。')
    } catch (error) {
      setMessage(accountErrorMessage(error))
    } finally {
      setExporting(false)
    }
  }

  const deleteAccount = async () => {
    if (confirmation !== '删除账号') {
      setMessage('请输入“删除账号”进行最终确认。')
      return
    }
    if (password.length < 10) {
      setMessage('请输入当前账号密码。')
      return
    }
    setDeleting(true)
    setMessage(null)
    try {
      await deletePilotAccount(password)
      window.location.assign('/login')
    } catch (error) {
      setMessage(accountErrorMessage(error))
      setDeleting(false)
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold text-slate-900">账号与私有数据</h3>
          <p className="mt-1 max-w-2xl text-[12px] leading-5 text-slate-500">
            可导出当前账号保存的私有资源、跟进和推荐反馈。删除账号会删除云端账号数据；不会自动清除本浏览器里以前的试用数据。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void exportData()}
          disabled={exporting || deleting}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12px] font-medium text-slate-700 disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          {exporting ? '正在导出…' : '导出我的数据'}
        </button>
      </div>

      <div className="mt-4 border-t border-slate-100 pt-4">
        {!deleteOpen ? (
          <button
            type="button"
            onClick={() => {
              setDeleteOpen(true)
              setMessage(null)
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] font-medium text-rose-800"
          >
            <Trash2 className="h-3.5 w-3.5" />
            删除账号
          </button>
        ) : (
          <div className="max-w-lg rounded-xl border border-rose-200 bg-rose-50 p-3">
            <p className="text-[12px] font-medium text-rose-900">删除后无法通过当前账号恢复云端私有数据。</p>
            <div className="mt-3 space-y-2">
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="当前账号密码"
                className="w-full rounded-lg border border-rose-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-rose-400"
              />
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder="输入：删除账号"
                className="w-full rounded-lg border border-rose-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-rose-400"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={deleting}
                  onClick={() => void deleteAccount()}
                  className="rounded-lg bg-rose-700 px-3 py-2 text-[12px] font-medium text-white disabled:opacity-50"
                >
                  {deleting ? '正在删除…' : '确认永久删除'}
                </button>
                <button
                  type="button"
                  disabled={deleting}
                  onClick={() => {
                    setDeleteOpen(false)
                    setPassword('')
                    setConfirmation('')
                    setMessage(null)
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12px] text-slate-700 disabled:opacity-50"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {message ? (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[12px] leading-5 text-slate-600">
          {message}
        </p>
      ) : null}
    </section>
  )
}
