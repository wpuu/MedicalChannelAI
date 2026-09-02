import { Plus, Save, ShieldCheck, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { AccountDataCard } from '@/components/profile/AccountDataCard'
import { LocalProfileImportCard } from '@/components/profile/LocalProfileImportCard'
import type { CapabilityType, RelationshipStrength } from '@/types'
import { useToast } from '@/context/ToastContext'
import {
  emptyLocalCustomerProfile,
  isSpecificCapabilityKeyword,
  type LocalCustomerProfile,
} from '@/services/localCustomerProfile'
import {
  clearCustomerProfile,
  loadCustomerProfile,
  saveCustomerProfile,
} from '@/services/profileApi'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'

const CAPABILITY_OPTIONS: CapabilityType[] = [
  'DIRECT_AUTHORIZED',
  'DIRECT_UNCONFIRMED',
  'NEED_MANUFACTURER',
  'PARTNER',
  'RENTAL_CAPABLE',
  'CAN_SOURCE_PARTNER',
  'SERVICE_ONLY',
]
const RELATIONSHIP_OPTIONS: RelationshipStrength[] = [
  'STRONG', 'MEDIUM', 'HISTORICAL', 'WEAK',
]

function TriStateSelect({ value, onChange }: {
  value: boolean | null
  onChange: (value: boolean | null) => void
}) {
  return (
    <select
      value={value === null ? 'unknown' : value ? 'yes' : 'no'}
      onChange={(event) => {
        const next = event.target.value
        onChange(next === 'yes' ? true : next === 'no' ? false : null)
      }}
      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-teal-500"
    >
      <option value="unknown">未确认</option>
      <option value="yes">可以</option>
      <option value="no">不可以</option>
    </select>
  )
}

export function PilotResourcesPage() {
  const { toast } = useToast()
  const [profile, setProfile] = useState<LocalCustomerProfile>(() => emptyLocalCustomerProfile())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    let active = true
    void loadCustomerProfile()
      .then((value) => {
        if (!active) return
        setProfile(value)
        setLoadError(false)
      })
      .catch(() => {
        if (active) setLoadError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const save = async () => {
    const ignoredGenericCount = profile.product_capabilities.filter(
      (item) => item.keyword.trim() && !isSpecificCapabilityKeyword(item.keyword),
    ).length
    setSaving(true)
    try {
      const saved = await saveCustomerProfile(profile)
      setProfile(saved)
      toast(
        ignoredGenericCount > 0
          ? `资源已保存到私有账号；${ignoredGenericCount} 个宽泛关键词不会参与高分匹配`
          : '资源已保存到私有账号',
        'success',
      )
    } catch {
      toast('保存失败，服务器原数据未被本次失败操作替换')
    } finally {
      setSaving(false)
    }
  }

  const clear = async () => {
    setSaving(true)
    try {
      const cleared = await clearCustomerProfile()
      setProfile(cleared)
      toast('账号中的产品能力、目标医院和医院关系已清空', 'success')
    } catch {
      toast('清空失败，请检查网络后重试')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">正在加载账号私有资源…</div>
  }
  if (loadError) {
    return (
      <div className="rounded-2xl border border-rose-100 bg-white p-6">
        <h2 className="font-semibold text-slate-900">无法读取私有资源</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">系统不会退回浏览器本地数据，避免把上一位用户或旧试用数据误当成当前账号的数据。</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-4 rounded-lg bg-teal-700 px-4 py-2 text-sm text-white">重试</button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">我的资源</h2>
            <p className="mt-1 max-w-3xl text-[13px] leading-6 text-slate-500">
              可选填写。目标医院表示“想持续关注/开发”，医院关系只表示你自己确认过的现有关系；二者独立，不从公开联系人反推私人关系。
            </p>
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 ring-1 ring-teal-200">
            <ShieldCheck className="h-3.5 w-3.5" />
            账号私有数据库
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2.5 text-[12px] leading-5 text-teal-900">
          这些数据与医院公开采购事实分开存储，并按当前登录用户隔离。目标医院不会自动算成“有关系”，也不会增加医院关系分。公开试用阶段曾保存在本机的数据不会自动上传。
        </div>
      </section>

      <LocalProfileImportCard
        accountProfile={profile}
        disabled={saving}
        onImported={setProfile}
      />

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-[15px] font-semibold text-slate-900">产品 / 服务能力</h3>
            <p className="mt-1 text-[12px] leading-5 text-slate-500">填写具体产品或能力，例如“生化分析仪”“DR”“病原微生物质谱”“医疗设备租赁”。</p>
          </div>
          <button
            type="button"
            onClick={() => setProfile((current) => ({
              ...current,
              product_capabilities: [
                ...current.product_capabilities,
                { keyword: '', capability_type: 'DIRECT_UNCONFIRMED' },
              ],
            }))}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600 hover:bg-slate-50"
          >
            <Plus className="h-3.5 w-3.5" /> 添加能力
          </button>
        </div>
        {profile.product_capabilities.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-5 text-center text-[13px] text-slate-400">暂未填写产品能力。</div>
        ) : (
          <div className="mt-4 space-y-2.5">
            {profile.product_capabilities.map((item, index) => {
              const tooGeneric = Boolean(item.keyword.trim()) && !isSpecificCapabilityKeyword(item.keyword)
              return (
                <div key={`${index}-${item.capability_type}`} className="rounded-xl bg-slate-50 p-3">
                  <div className="grid gap-2 md:grid-cols-[1fr_240px_auto]">
                    <input
                      value={item.keyword}
                      placeholder="产品 / 服务关键词"
                      onChange={(event) => {
                        const keyword = event.target.value
                        setProfile((current) => ({
                          ...current,
                          product_capabilities: current.product_capabilities.map((row, rowIndex) => rowIndex === index ? { ...row, keyword } : row),
                        }))
                      }}
                      className={`rounded-lg border bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-500 ${tooGeneric ? 'border-amber-300' : 'border-slate-200'}`}
                    />
                    <select
                      value={item.capability_type}
                      onChange={(event) => {
                        const capability_type = event.target.value as CapabilityType
                        setProfile((current) => ({
                          ...current,
                          product_capabilities: current.product_capabilities.map((row, rowIndex) => rowIndex === index ? { ...row, capability_type } : row),
                        }))
                      }}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-teal-500"
                    >
                      {CAPABILITY_OPTIONS.map((value) => <option key={value} value={value}>{CAPABILITY_LABEL[value]}</option>)}
                    </select>
                    <button
                      type="button"
                      title="删除"
                      onClick={() => setProfile((current) => ({
                        ...current,
                        product_capabilities: current.product_capabilities.filter((_, rowIndex) => rowIndex !== index),
                      }))}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white hover:text-rose-600"
                    ><Trash2 className="h-4 w-4" /></button>
                  </div>
                  {tooGeneric ? <p className="mt-2 text-[11px] leading-5 text-amber-700">关键词过于宽泛，不会参与产品匹配加分。</p> : null}
                </div>
              )
            })}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-[15px] font-semibold text-slate-900">目标医院 / 重点关注</h3>
            <p className="mt-1 text-[12px] leading-5 text-slate-500">可以关注当前完全没有关系的医院。这里表示经营意图/监控范围，不代表院内关系，也不增加关系分。</p>
          </div>
          <button
            type="button"
            onClick={() => setProfile((current) => ({
              ...current,
              target_hospitals: [
                ...current.target_hospitals,
                { hospital: '', department: null },
              ],
            }))}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600 hover:bg-slate-50"
          ><Plus className="h-3.5 w-3.5" /> 添加目标医院</button>
        </div>
        {profile.target_hospitals.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-5 text-center text-[13px] text-slate-400">暂未设置目标医院。没有关系也可以加入关注。</div>
        ) : (
          <div className="mt-4 space-y-2.5">
            {profile.target_hospitals.map((item, index) => (
              <div key={`${index}-${item.hospital}`} className="grid gap-2 rounded-xl bg-slate-50 p-3 lg:grid-cols-[1.3fr_1fr_auto]">
                <input
                  value={item.hospital}
                  placeholder="医院 / 采购单位"
                  onChange={(event) => {
                    const hospital = event.target.value
                    setProfile((current) => ({
                      ...current,
                      target_hospitals: current.target_hospitals.map((row, rowIndex) => rowIndex === index ? { ...row, hospital } : row),
                    }))
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-500"
                />
                <input
                  value={item.department ?? ''}
                  placeholder="重点科室（留空=全院）"
                  onChange={(event) => {
                    const department = event.target.value || null
                    setProfile((current) => ({
                      ...current,
                      target_hospitals: current.target_hospitals.map((row, rowIndex) => rowIndex === index ? { ...row, department } : row),
                    }))
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-500"
                />
                <button
                  type="button"
                  title="取消关注"
                  onClick={() => setProfile((current) => ({
                    ...current,
                    target_hospitals: current.target_hospitals.filter((_, rowIndex) => rowIndex !== index),
                  }))}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white hover:text-rose-600"
                ><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-[15px] font-semibold text-slate-900">医院关系</h3>
            <p className="mt-1 text-[12px] leading-5 text-slate-500">只填你自己确认过的现有/历史关系；是否是目标医院由上面的“重点关注”独立决定。</p>
          </div>
          <button
            type="button"
            onClick={() => setProfile((current) => ({
              ...current,
              hospital_relationships: [
                ...current.hospital_relationships,
                { hospital: '', department: null, relationship_strength: 'MEDIUM' },
              ],
            }))}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600 hover:bg-slate-50"
          ><Plus className="h-3.5 w-3.5" /> 添加关系</button>
        </div>
        {profile.hospital_relationships.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-5 text-center text-[13px] text-slate-400">暂未填写医院关系。</div>
        ) : (
          <div className="mt-4 space-y-2.5">
            {profile.hospital_relationships.map((item, index) => (
              <div key={`${index}-${item.relationship_strength}`} className="grid gap-2 rounded-xl bg-slate-50 p-3 lg:grid-cols-[1.3fr_1fr_180px_auto]">
                <input
                  value={item.hospital}
                  placeholder="医院 / 采购单位"
                  onChange={(event) => {
                    const hospital = event.target.value
                    setProfile((current) => ({
                      ...current,
                      hospital_relationships: current.hospital_relationships.map((row, rowIndex) => rowIndex === index ? { ...row, hospital } : row),
                    }))
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-500"
                />
                <input
                  value={item.department ?? ''}
                  placeholder="关系科室（留空=全院）"
                  onChange={(event) => {
                    const department = event.target.value || null
                    setProfile((current) => ({
                      ...current,
                      hospital_relationships: current.hospital_relationships.map((row, rowIndex) => rowIndex === index ? { ...row, department } : row),
                    }))
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-500"
                />
                <select
                  value={item.relationship_strength}
                  onChange={(event) => {
                    const relationship_strength = event.target.value as RelationshipStrength
                    setProfile((current) => ({
                      ...current,
                      hospital_relationships: current.hospital_relationships.map((row, rowIndex) => rowIndex === index ? { ...row, relationship_strength } : row),
                    }))
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-teal-500"
                >
                  {RELATIONSHIP_OPTIONS.map((value) => <option key={value} value={value}>{RELATIONSHIP_LABEL[value]}</option>)}
                </select>
                <button
                  type="button"
                  title="删除"
                  onClick={() => setProfile((current) => ({
                    ...current,
                    hospital_relationships: current.hospital_relationships.filter((_, rowIndex) => rowIndex !== index),
                  }))}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white hover:text-rose-600"
                ><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-[15px] font-semibold text-slate-900">合作能力</h3>
        <p className="mt-1 text-[12px] leading-5 text-slate-500">用于判断没有现成产品时能否通过厂家、渠道或租赁参与。</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="space-y-1.5 text-[12px] text-slate-600"><span>可临时寻找厂家</span><TriStateSelect value={profile.can_find_manufacturer} onChange={(value) => setProfile((current) => ({ ...current, can_find_manufacturer: value }))} /></label>
          <label className="space-y-1.5 text-[12px] text-slate-600"><span>可与其他渠道合作</span><TriStateSelect value={profile.can_partner_channel} onChange={(value) => setProfile((current) => ({ ...current, can_partner_channel: value }))} /></label>
          <label className="space-y-1.5 text-[12px] text-slate-600"><span>可参与租赁项目</span><TriStateSelect value={profile.can_handle_lease} onChange={(value) => setProfile((current) => ({ ...current, can_handle_lease: value }))} /></label>
        </div>
      </section>

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" disabled={saving} onClick={() => void clear()} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] text-slate-600 hover:bg-slate-50 disabled:opacity-50">清空账号资源</button>
        <button type="button" disabled={saving} onClick={() => void save()} className="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 px-4 py-2 text-[13px] font-medium text-white hover:bg-teal-800 disabled:opacity-50"><Save className="h-4 w-4" />{saving ? '保存中…' : '保存到账号'}</button>
      </div>

      <AccountDataCard />
    </div>
  )
}
