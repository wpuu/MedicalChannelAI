import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, Loader2, Save } from 'lucide-react'
import { useToast } from '@/context/ToastContext'
import { isAuthRequiredError } from '@/services/apiConfig'
import {
  getCustomerProfile,
  updateCustomerProfile,
  type BusinessRole,
  type CapabilityType,
  type CustomerProfileEditable,
  type ProfileReadiness,
  type RelationshipStrength,
} from '@/services/profileApi'

const PRODUCTS = [
  ['PHLEBOTOMY_COLLECTION_TABLE', '采血台 / 智能采血工作台'],
  ['LAB_BIOCHEMISTRY_ANALYZER', '生化分析设备'],
  ['LAB_CHEMILUMINESCENCE_ANALYZER', '化学发光免疫分析设备'],
  ['LAB_COAGULATION_ANALYZER', '凝血分析设备'],
  ['LAB_HEMATOLOGY_ANALYZER', '血细胞分析设备'],
  ['LAB_URINALYSIS_ANALYZER', '尿液分析设备'],
  ['LAB_PCR_QPCR', 'PCR / qPCR 分子检测设备'],
  ['LAB_FLOW_CYTOMETER', '流式细胞仪'],
  ['LAB_AUTOMATION_LINE', '检验自动化 / 生化免疫流水线'],
  ['LAB_SAMPLE_PREPROCESSING', '样本前处理设备'],
  ['LAB_REAGENT_IMMUNOASSAY', '免疫 / 化学发光检测试剂'],
  ['LAB_REAGENT_MOLECULAR', '分子 / 核酸检测试剂'],
  ['LAB_REAGENT_GENERAL', '检验试剂通用'],
  ['MEDICAL_IMAGING_ULTRASOUND', '超声设备'],
  ['MEDICAL_IMAGING_CT', 'CT'],
  ['MEDICAL_IMAGING_MRI', '磁共振 MRI'],
  ['MEDICAL_IMAGING_DR', '数字 X 线摄影 DR'],
  ['MEDICAL_CONSUMABLE_GENERAL', '医疗耗材通用'],
  ['MEDICAL_DEVICE_DIGITAL_MANAGEMENT', '医疗设备数字化管理系统'],
] as const

const CUSTOMER_TYPES = [
  ['TERTIARY_HOSPITAL', '三甲 / 三级医院'],
  ['SECONDARY_HOSPITAL', '二级医院'],
  ['PRIMARY_CARE', '基层医疗'],
  ['PRIVATE_HOSPITAL', '民营医院'],
  ['CDC', '疾控'],
  ['BLOOD_CENTER', '血站'],
  ['UNIVERSITY', '高校'],
  ['RESEARCH_INSTITUTE', '科研机构'],
  ['THIRD_PARTY_LAB', '第三方检验'],
] as const

const STAGES = [
  ['MARKET_RESEARCH', '市场调研'],
  ['PROCUREMENT_INTENT', '采购意向'],
  ['PREPARING', '筹备中'],
  ['TENDERING', '正式招标'],
  ['AMENDED', '变更公告'],
  ['BID_CLOSED', '已截标'],
  ['AWARDED', '中标结果'],
] as const

const ROLE_OPTIONS: Array<[BusinessRole, string]> = [
  ['LOCAL_DISTRIBUTOR', '本地经销商'],
  ['REGIONAL_DISTRIBUTOR', '区域经销商'],
  ['MANUFACTURER_SALES', '厂家一线销售'],
  ['MANUFACTURER_CHANNEL_MANAGER', '厂家渠道负责人'],
  ['OTHER', '其他'],
]

const CAPABILITY_OPTIONS: Array<[CapabilityType, string]> = [
  ['DIRECT_AUTHORIZED', '已有授权 / 可直接销售'],
  ['DIRECT_UNCONFIRMED', '有资源，可直接推进但授权待确认'],
  ['CAN_SOURCE_PARTNER', '没有现成授权，但能找厂家合作'],
  ['RENTAL_CAPABLE', '可做租赁 / 服务方案'],
  ['SERVICE_ONLY', '只做服务'],
]

interface ProductFormState {
  selected: boolean
  capability_type: CapabilityType
  brands: string
}

function emptyProducts(): Record<string, ProductFormState> {
  return Object.fromEntries(
    PRODUCTS.map(([id]) => [id, { selected: false, capability_type: 'CAN_SOURCE_PARTNER', brands: '' }]),
  )
}

function splitBrands(value: string): string[] {
  return value
    .split(/[，,、\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function relationshipLabel(value: RelationshipStrength): string {
  if (value === 'STRONG') return '强'
  if (value === 'MEDIUM') return '中'
  if (value === 'WEAK') return '弱'
  if (value === 'HISTORICAL') return '历史'
  return '未知'
}

function parseStrength(value: string): RelationshipStrength {
  const normalized = value.trim().toLowerCase()
  if (['强', 'strong', '强关系'].includes(normalized)) return 'STRONG'
  if (['中', 'medium', '一般', '中等'].includes(normalized)) return 'MEDIUM'
  if (['弱', 'weak'].includes(normalized)) return 'WEAK'
  if (['历史', 'historical', '以前'].includes(normalized)) return 'HISTORICAL'
  return 'UNKNOWN'
}

function relationshipsToText(profile: CustomerProfileEditable): string {
  return profile.hospital_relationships
    .map((item) =>
      [
        item.hospital_name,
        item.department ?? '',
        relationshipLabel(item.relationship_strength),
        item.owner ?? '',
      ].join(' | '),
    )
    .join('\n')
}

function parseRelationships(value: string): CustomerProfileEditable['hospital_relationships'] {
  const now = new Date().toISOString()
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [hospital = '', department = '', strength = '', owner = ''] = line
        .split('|')
        .map((part) => part.trim())
      return {
        hospital_name: hospital,
        department: department || null,
        relationship_strength: parseStrength(strength),
        owner: owner || null,
        confirmed_by_customer: true,
        last_confirmed_at: now,
      }
    })
    .filter((item) => item.hospital_name.length > 0)
}

export function ProfilePage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [companyName, setCompanyName] = useState('')
  const [businessRole, setBusinessRole] = useState<BusinessRole>('LOCAL_DISTRIBUTOR')
  const [customerTypes, setCustomerTypes] = useState<string[]>(['TERTIARY_HOSPITAL', 'SECONDARY_HOSPITAL'])
  const [products, setProducts] = useState<Record<string, ProductFormState>>(emptyProducts)
  const [minimumAmount, setMinimumAmount] = useState('100000')
  const [preferredStages, setPreferredStages] = useState<string[]>(['PROCUREMENT_INTENT', 'PREPARING', 'TENDERING'])
  const [canFindManufacturer, setCanFindManufacturer] = useState(true)
  const [canPartnerChannel, setCanPartnerChannel] = useState(true)
  const [canLease, setCanLease] = useState(true)
  const [relationships, setRelationships] = useState('')
  const [readiness, setReadiness] = useState<ProfileReadiness | null>(null)

  const selectedProductCount = useMemo(
    () => Object.values(products).filter((item) => item.selected).length,
    [products],
  )

  useEffect(() => {
    const load = async () => {
      try {
        const envelope = await getCustomerProfile()
        const profile = envelope.profile
        setCompanyName(profile.company_name || '')
        setBusinessRole(profile.business_role || 'LOCAL_DISTRIBUTOR')
        setCustomerTypes(profile.customer_types || [])
        setMinimumAmount(profile.opportunity_thresholds?.minimum_project_amount_cny || '100000')
        setPreferredStages(profile.opportunity_thresholds?.preferred_stages || [])
        setCanFindManufacturer(Boolean(profile.partnering_policy?.can_seek_temporary_manufacturer))
        setCanPartnerChannel(Boolean(profile.partnering_policy?.can_cooperate_with_channel_partner))
        setCanLease(Boolean(profile.partnering_policy?.can_do_rental_projects))
        setRelationships(relationshipsToText(profile))
        const next = emptyProducts()
        for (const capability of profile.product_capabilities || []) {
          for (const taxonomyId of capability.taxonomy_ids || []) {
            if (!next[taxonomyId]) continue
            next[taxonomyId] = {
              selected: true,
              capability_type: capability.capability_type,
              brands: (capability.brands || []).join('、'),
            }
          }
        }
        setProducts(next)
        setReadiness(envelope.readiness)
      } catch (cause) {
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        toast('客户资料加载失败，请重试')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [navigate, toast])

  const toggleValue = (values: string[], value: string) =>
    values.includes(value) ? values.filter((item) => item !== value) : [...values, value]

  const save = async () => {
    const productCapabilities = PRODUCTS.flatMap(([id, label]) => {
      const state = products[id]
      if (!state?.selected) return []
      return [
        {
          category: label,
          subcategory: null,
          taxonomy_ids: [id],
          brands: splitBrands(state.brands),
          capability_type: state.capability_type,
          notes: null,
        },
      ]
    })

    const payload: CustomerProfileEditable = {
      company_name: companyName.trim(),
      business_role: businessRole,
      operating_regions: [
        {
          province: '天津市',
          city: '天津市',
          scope_mode: 'ENTIRE_CITY',
          districts: [],
        },
      ],
      customer_types: customerTypes,
      product_capabilities: productCapabilities,
      partnering_policy: {
        can_seek_temporary_manufacturer: canFindManufacturer,
        can_cooperate_with_channel_partner: canPartnerChannel,
        can_do_rental_projects: canLease,
      },
      opportunity_thresholds: {
        minimum_project_amount_cny: minimumAmount.trim() || '0',
        preferred_stages: preferredStages,
      },
      exclusion_rules: [],
      hospital_relationships: parseRelationships(relationships),
      confirmation_flags: {
        region_scope_confirmed: true,
        customer_types_confirmed: true,
        product_capabilities_confirmed: true,
        partnering_policy_confirmed: true,
        opportunity_preferences_confirmed: true,
        exclusion_rules_confirmed: true,
      },
    }

    setSaving(true)
    try {
      const envelope = await updateCustomerProfile(payload)
      setReadiness(envelope.readiness)
      if (envelope.readiness.candidate_opportunity_allowed) {
        toast('资料已保存。今日行动会按新画像重新匹配并触发需要的 Agnes 分析。', 'success')
      } else {
        toast(envelope.readiness.next_question || '资料已保存，但仍缺少必要信息。')
      }
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('资料保存失败，请检查填写内容后重试')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 加载客户资料…
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">我的业务资料</h2>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">
              这些信息只用于匹配、排序和生成你的销售动作，不会当作官方采购事实。
            </p>
          </div>
          {readiness ? (
            <div className="rounded-xl bg-slate-50 px-3 py-2 text-right">
              <div className="text-[11px] text-slate-500">资料完整度</div>
              <div className="text-lg font-semibold text-teal-700">{readiness.profile_completeness}%</div>
            </div>
          ) : null}
        </div>
        {readiness?.personalized_recommendation_allowed ? (
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800">
            <CheckCircle2 className="h-4 w-4" /> 已具备个性化推荐条件
          </div>
        ) : readiness?.next_question ? (
          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] leading-5 text-amber-900">
            还需要确认：{readiness.next_question}
          </div>
        ) : null}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div>
            <label className="mb-1 block text-[13px] font-medium text-slate-700">公司 / 团队名称</label>
            <input
              value={companyName}
              onChange={(event) => setCompanyName(event.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-teal-600"
              placeholder="例如：天津多克隆商贸"
            />
          </div>
          <div>
            <label className="mb-1 block text-[13px] font-medium text-slate-700">当前角色</label>
            <select
              value={businessRole}
              onChange={(event) => setBusinessRole(event.target.value as BusinessRole)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            >
              {ROLE_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div>
            <div className="mb-2 text-[13px] font-medium text-slate-700">主要客户类型</div>
            <div className="grid grid-cols-2 gap-2">
              {CUSTOMER_TYPES.map(([value, label]) => (
                <label key={value} className="flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-2 text-[12px] text-slate-700">
                  <input
                    type="checkbox"
                    checked={customerTypes.includes(value)}
                    onChange={() => setCustomerTypes((items) => toggleValue(items, value))}
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div>
            <div className="mb-2 text-[13px] font-medium text-slate-700">合作与执行能力</div>
            {[
              [canFindManufacturer, setCanFindManufacturer, '没有现成厂家时，可以临时找厂家合作'],
              [canPartnerChannel, setCanPartnerChannel, '可以和其他渠道商联合做项目'],
              [canLease, setCanLease, '可以做设备租赁 / 租赁服务项目'],
            ].map(([checked, setter, label]) => (
              <label key={String(label)} className="mb-2 flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 text-[13px] text-slate-700">
                <input
                  type="checkbox"
                  checked={Boolean(checked)}
                  onChange={(event) => (setter as (value: boolean) => void)(event.target.checked)}
                  className="mt-0.5"
                />
                {String(label)}
              </label>
            ))}
          </div>
          <div>
            <label className="mb-1 block text-[13px] font-medium text-slate-700">最低值得跟进的项目金额（元）</label>
            <input
              value={minimumAmount}
              onChange={(event) => setMinimumAmount(event.target.value.replace(/[^0-9.]/g, ''))}
              inputMode="decimal"
              className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <div className="mb-2 text-[13px] font-medium text-slate-700">希望重点看到的阶段</div>
            <div className="flex flex-wrap gap-2">
              {STAGES.map(([value, label]) => (
                <label key={value} className="flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1.5 text-[12px]">
                  <input
                    type="checkbox"
                    checked={preferredStages.includes(value)}
                    onChange={() => setPreferredStages((items) => toggleValue(items, value))}
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h3 className="text-[15px] font-semibold text-slate-900">产品与资源</h3>
            <p className="mt-1 text-[12px] text-slate-500">先勾选真正能做或能找到合作资源的产品。已选 {selectedProductCount} 项。</p>
          </div>
        </div>
        <div className="mt-3 grid gap-2 lg:grid-cols-2">
          {PRODUCTS.map(([id, label]) => {
            const state = products[id]
            return (
              <div key={id} className="rounded-xl border border-slate-200 p-3">
                <label className="flex items-center gap-2 text-[13px] font-medium text-slate-800">
                  <input
                    type="checkbox"
                    checked={state.selected}
                    onChange={(event) =>
                      setProducts((items) => ({
                        ...items,
                        [id]: { ...items[id], selected: event.target.checked },
                      }))
                    }
                  />
                  {label}
                </label>
                {state.selected ? (
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <select
                      value={state.capability_type}
                      onChange={(event) =>
                        setProducts((items) => ({
                          ...items,
                          [id]: { ...items[id], capability_type: event.target.value as CapabilityType },
                        }))
                      }
                      className="rounded-lg border border-slate-300 px-2 py-1.5 text-[12px]"
                    >
                      {CAPABILITY_OPTIONS.map(([value, text]) => (
                        <option key={value} value={value}>{text}</option>
                      ))}
                    </select>
                    <input
                      value={state.brands}
                      onChange={(event) =>
                        setProducts((items) => ({
                          ...items,
                          [id]: { ...items[id], brands: event.target.value },
                        }))
                      }
                      placeholder="品牌，可空"
                      className="rounded-lg border border-slate-300 px-2 py-1.5 text-[12px]"
                    />
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-[15px] font-semibold text-slate-900">医院关系</h3>
        <p className="mt-1 text-[12px] leading-5 text-slate-500">
          每行一条：医院名称 | 科室 | 关系强度（强/中/弱/历史） | 内部负责人。没有关系的医院不用填。
        </p>
        <textarea
          value={relationships}
          onChange={(event) => setRelationships(event.target.value)}
          rows={6}
          placeholder={'天津某医院 | 检验科 | 强 | 老杨\n天津某医院 | 设备科 | 中 | 老杨'}
          className="mt-3 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm leading-6 outline-none focus:border-teal-600"
        />
      </section>

      <div className="sticky bottom-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg backdrop-blur">
        <p className="text-[12px] leading-5 text-slate-500">
          保存后，今日行动会使用这份客户确认资料重新匹配；需要 AI 判断的 Top 5 才会进入 Agnes 队列。
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => navigate('/today')}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
          >
            查看今日行动
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void save()}
            className="inline-flex items-center gap-2 rounded-xl bg-teal-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            保存资料
          </button>
        </div>
      </div>
    </div>
  )
}
