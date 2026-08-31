import { Plus, Save, ShieldCheck, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { CapabilityType, RelationshipStrength } from '@/types'
import { useToast } from '@/context/ToastContext'
import {
  clearLocalCustomerProfile,
  isSpecificCapabilityKeyword,
  loadLocalCustomerProfile,
  saveLocalCustomerProfile,
  type LocalCustomerProfile,
} from '@/services/localCustomerProfile'
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
  'STRONG',
  'MEDIUM',
  'HISTORICAL',
  'WEAK',
]

function TriStateSelect({
  value,
  onChange,
}: {
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

export function ResourcesPage() {
  const { toast } = useToast()
  const [profile, setProfile] = useState<LocalCustomerProfile>(() => loadLocalCustomerProfile())

  const save = () => {
    const ignoredGenericCount = profile.product_capabilities.filter(
      (item) => item.keyword.trim() && !isSpecificCapabilityKeyword(item.keyword),
    ).length
    saveLocalCustomerProfile(profile)
    toast(
      ignoredGenericCount > 0
        ? `资源已保存；${ignoredGenericCount} 个过于宽泛的关键词不会参与高分匹配`
        : '资源已保存在当前浏览器，将重新计算商机排序',
      'success',
    )
    window.setTimeout(() => window.location.assign('/today'), 250)
  }

  const clear = () => {
    clearLocalCustomerProfile()
    toast('本地资源已清空', 'success')
    window.setTimeout(() => window.location.assign('/today'), 250)
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">我的资源</h2>
            <p className="mt-1 max-w-3xl text-[13px] leading-6 text-slate-500">
              可选填写。零配置也能继续看公开商机；填写后，系统才会把你的产品能力和医院关系加入经营优先级排序。
            </p>
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-lg bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 ring-1 ring-teal-200">
            <ShieldCheck className="h-3.5 w-3.5" />
            当前浏览器本地保存
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2.5 text-[12px] leading-5 text-amber-900">
          这些内容属于你自己确认的业务资源，不是医院公开事实。系统会明确区分两类数据；填写医院关系也不会被展示成医院官方信息。
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-[15px] font-semibold text-slate-900">产品 / 服务能力</h3>
            <p className="mt-1 text-[12px] leading-5 text-slate-500">
              尽量填写具体产品或能力，例如“生化分析仪”“DR”“病原微生物质谱”“医疗设备租赁”。“医疗”“设备”“服务”等过于宽泛的词可以保存，但不会用于高分匹配。
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              setProfile((current) => ({
                ...current,
                product_capabilities: [
                  ...current.product_capabilities,
                  { keyword: '', capability_type: 'DIRECT_UNCONFIRMED' },
                ],
              }))
            }
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600 hover:bg-slate-50"
          >
            <Plus className="h-3.5 w-3.5" />
            添加能力
          </button>
        </div>

        {profile.product_capabilities.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-5 text-center text-[13px] text-slate-400">
            暂未填写产品能力。当前商机仍只按公开事实排序。
          </div>
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
                          product_capabilities: current.product_capabilities.map((row, rowIndex) =>
                            rowIndex === index ? { ...row, keyword } : row,
                          ),
                        }))
                      }}
                      className={`rounded-lg border bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-500 ${
                        tooGeneric ? 'border-amber-300' : 'border-slate-200'
                      }`}
                    />
                    <select
                      value={item.capability_type}
                      onChange={(event) => {
                        const capability_type = event.target.value as CapabilityType
                        setProfile((current) => ({
                          ...current,
                          product_capabilities: current.product_capabilities.map((row, rowIndex) =>
                            rowIndex === index ? { ...row, capability_type } : row,
                          ),
                        }))
                      }}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-teal-500"
                    >
                      {CAPABILITY_OPTIONS.map((value) => (
                        <option key={value} value={value}>
                          {CAPABILITY_LABEL[value]}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      title="删除"
                      onClick={() =>
                        setProfile((current) => ({
                          ...current,
                          product_capabilities: current.product_capabilities.filter((_, rowIndex) => rowIndex !== index),
                        }))
                      }
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white hover:text-rose-600"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  {tooGeneric ? (
                    <p className="mt-2 text-[11px] leading-5 text-amber-700">
                      这个关键词过于宽泛，不会参与产品匹配加分。请改成更具体的产品、设备、检验项目或服务类型。
                    </p>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-[15px] font-semibold text-slate-900">医院关系</h3>
            <p className="mt-1 text-[12px] leading-5 text-slate-500">
              只填你自己确认过的关系。医院名称与公开采购单位匹配后才会影响排序；如果填写了具体关系科室，这条关系只对同科室项目生效，不会自动扩大为全院关系。
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              setProfile((current) => ({
                ...current,
                hospital_relationships: [
                  ...current.hospital_relationships,
                  { hospital: '', department: null, relationship_strength: 'MEDIUM' },
                ],
              }))
            }
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600 hover:bg-slate-50"
          >
            <Plus className="h-3.5 w-3.5" />
            添加关系
          </button>
        </div>

        {profile.hospital_relationships.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-200 px-4 py-5 text-center text-[13px] text-slate-400">
            暂未填写医院关系。系统不会从公开联系人或历史项目推断你的院内关系。
          </div>
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
                      hospital_relationships: current.hospital_relationships.map((row, rowIndex) =>
                        rowIndex === index ? { ...row, hospital } : row,
                      ),
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
                      hospital_relationships: current.hospital_relationships.map((row, rowIndex) =>
                        rowIndex === index ? { ...row, department } : row,
                      ),
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
                      hospital_relationships: current.hospital_relationships.map((row, rowIndex) =>
                        rowIndex === index ? { ...row, relationship_strength } : row,
                      ),
                    }))
                  }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 outline-none focus:border-teal-500"
                >
                  {RELATIONSHIP_OPTIONS.map((value) => (
                    <option key={value} value={value}>
                      {RELATIONSHIP_LABEL[value]}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  title="删除"
                  onClick={() =>
                    setProfile((current) => ({
                      ...current,
                      hospital_relationships: current.hospital_relationships.filter((_, rowIndex) => rowIndex !== index),
                    }))
                  }
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-white hover:text-rose-600"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-[15px] font-semibold text-slate-900">合作能力</h3>
        <p className="mt-1 text-[12px] leading-5 text-slate-500">
          用于以后判断“没有现成产品但能否借助厂家、渠道或租赁模式参与”。未确认就保持“未确认”。
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="space-y-1.5 text-[12px] text-slate-600">
            <span>可临时寻找厂家</span>
            <TriStateSelect
              value={profile.can_find_manufacturer}
              onChange={(value) => setProfile((current) => ({ ...current, can_find_manufacturer: value }))}
            />
          </label>
          <label className="space-y-1.5 text-[12px] text-slate-600">
            <span>可与其他渠道合作</span>
            <TriStateSelect
              value={profile.can_partner_channel}
              onChange={(value) => setProfile((current) => ({ ...current, can_partner_channel: value }))}
            />
          </label>
          <label className="space-y-1.5 text-[12px] text-slate-600">
            <span>可参与租赁项目</span>
            <TriStateSelect
              value={profile.can_handle_lease}
              onChange={(value) => setProfile((current) => ({ ...current, can_handle_lease: value }))}
            />
          </label>
        </div>
      </section>

      <div className="flex flex-wrap justify-end gap-2 pb-4">
        <button
          type="button"
          onClick={clear}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] text-slate-600 hover:bg-slate-50"
        >
          清空我的资源
        </button>
        <button
          type="button"
          onClick={save}
          className="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 px-4 py-2 text-[13px] font-medium text-white hover:bg-teal-800"
        >
          <Save className="h-4 w-4" />
          保存并重新排序
        </button>
      </div>
    </div>
  )
}
