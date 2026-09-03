import { useMemo, useState } from 'react'
import { HardDrive, Upload } from 'lucide-react'
import { useToast } from '@/context/ToastContext'
import type { LocalCustomerProfile } from '@/services/localCustomerProfile'
import {
  clearImportedLocalProfile,
  loadImportableLocalProfile,
  mergeLocalProfileIntoAccount,
} from '@/services/profileMigration'
import { saveCustomerProfile } from '@/services/profileApi'

interface LocalProfileImportCardProps {
  accountProfile: LocalCustomerProfile
  disabled?: boolean
  onImported: (profile: LocalCustomerProfile) => void
}

export function LocalProfileImportCard({
  accountProfile,
  disabled = false,
  onImported,
}: LocalProfileImportCardProps) {
  const { toast } = useToast()
  const [localProfile, setLocalProfile] = useState<LocalCustomerProfile | null>(
    () => loadImportableLocalProfile(),
  )
  const [importing, setImporting] = useState(false)

  const counts = useMemo(() => ({
    products: localProfile?.product_capabilities.length ?? 0,
    targets: localProfile?.target_hospitals.length ?? 0,
    relationships: localProfile?.hospital_relationships.length ?? 0,
    preferences: localProfile
      ? [
          localProfile.can_find_manufacturer,
          localProfile.can_partner_channel,
          localProfile.can_handle_lease,
        ].filter((value) => value !== null).length
      : 0,
  }), [localProfile])

  if (!localProfile) return null

  const importToAccount = async () => {
    setImporting(true)
    try {
      const merged = mergeLocalProfileIntoAccount(accountProfile, localProfile)
      const saved = await saveCustomerProfile(merged)
      // The local trial profile is unowned legacy device data. Once the user has
      // explicitly migrated it into one authenticated account, consume the local
      // copy so a later account on the same browser cannot import it again.
      clearImportedLocalProfile()
      setLocalProfile(null)
      onImported(saved)
      toast('本机试用资源已合并到当前账号；旧本机副本已清除', 'success')
    } catch {
      toast('导入失败；本机数据和账号原数据都未被删除')
    } finally {
      setImporting(false)
    }
  }

  const clearLocalCopy = () => {
    clearImportedLocalProfile()
    setLocalProfile(null)
    toast('仅清除了这台设备上的旧试用资源；账号云端数据未改变', 'success')
  }

  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/60 p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-amber-700 ring-1 ring-amber-200">
          <HardDrive className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] font-semibold text-slate-900">检测到这台设备上的旧试用资源</h3>
          <p className="mt-1 text-[12px] leading-5 text-slate-600">
            本机有 {counts.products} 条产品/服务能力、{counts.targets} 个目标医院、{counts.relationships} 条医院关系、{counts.preferences} 项合作能力设置。系统不会自动上传这些数据。
          </p>
          <p className="mt-1 text-[11px] leading-5 text-slate-500">
            仅在确认这些旧试用资源属于你时导入。点击导入后才会发送到当前登录账号；云端保存成功后，本机旧副本会自动清除，避免以后被其他账号重复导入。合并时以账号现有数据优先。
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={disabled || importing}
              onClick={() => void importToAccount()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-amber-700 px-3 py-2 text-[12px] font-medium text-white hover:bg-amber-800 disabled:opacity-50"
            >
              <Upload className="h-3.5 w-3.5" />
              {importing ? '正在导入…' : '导入本机试用资源到当前账号'}
            </button>
            <button
              type="button"
              disabled={disabled || importing}
              onClick={clearLocalCopy}
              className="rounded-lg border border-amber-300 bg-white px-3 py-2 text-[12px] text-amber-900 hover:bg-amber-100 disabled:opacity-50"
            >
              仅清除本机副本
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
