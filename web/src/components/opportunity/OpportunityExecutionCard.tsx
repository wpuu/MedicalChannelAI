import { Building2, CheckCircle2, PackageSearch, Save, Target, Users, X } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useToast } from '@/context/ToastContext'
import { isAuthRequiredError } from '@/services/apiConfig'
import {
  emptyLocalCustomerProfile,
  isSpecificCapabilityKeyword,
  type LocalCustomerProfile,
} from '@/services/localCustomerProfile'
import { loadCustomerProfile, saveCustomerProfile } from '@/services/profileApi'
import type { CapabilityType, RelationshipStrength, TodayActionCard } from '@/types'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'

const RELATIONSHIP_OPTIONS: RelationshipStrength[] = ['STRONG', 'MEDIUM', 'HISTORICAL', 'WEAK']
const CAPABILITY_OPTIONS: CapabilityType[] = [
  'DIRECT_AUTHORIZED',
  'DIRECT_UNCONFIRMED',
  'NEED_MANUFACTURER',
  'PARTNER',
  'RENTAL_CAPABLE',
  'CAN_SOURCE_PARTNER',
  'SERVICE_ONLY',
]
const OBVIOUS_MEDICAL_INSTITUTION = /(医院|卫生院|社区卫生服务中心|妇幼保健院|妇幼保健中心|疾病预防控制中心|疾控中心|血液中心|医学中心|急救中心|疗养院)/
const PROJECT_CAPABILITY_HINTS = [
  { keyword: 'DSA', terms: ['数字减影血管造影', '血管造影机'] },
  { keyword: 'DR', terms: ['数字X光机', '数字X线摄影', '数字化X线摄影', '数字化X射线摄影'] },
  { keyword: 'CT', terms: ['CT机', 'CT影像', '计算机断层扫描', '电子计算机断层扫描'] },
  { keyword: 'MRI', terms: ['磁共振', '磁共振成像'] },
  { keyword: 'IVD', terms: ['体外诊断'] },
  { keyword: 'PCR', terms: ['聚合酶链式反应', '核酸扩增'] },
  { keyword: 'ECG', terms: ['心电图机'] },
] as const

function normalize(value: string | null | undefined): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s\-_—–·,，。；;：:（）()【】\[\]]+/g, '')
}

function medicalInstitutionBuyer(value: string | null | undefined): string | null {
  const name = value?.trim() || ''
  return name && OBVIOUS_MEDICAL_INSTITUTION.test(name) ? name : null
}

function sameScope(
  leftHospital: string,
  leftDepartment: string | null,
  rightHospital: string,
  rightDepartment: string | null,
): boolean {
  const left = normalize(leftHospital)
  const right = normalize(rightHospital)
  if (!left || !right || !(left === right || left.includes(right) || right.includes(left))) return false

  const leftDept = normalize(leftDepartment)
  const rightDept = normalize(rightDepartment)
  if (!leftDept || !rightDept) return true
  return leftDept === rightDept || leftDept.includes(rightDept) || rightDept.includes(leftDept)
}

function sameExactScope(
  leftHospital: string,
  leftDepartment: string | null,
  rightHospital: string,
  rightDepartment: string | null,
): boolean {
  return normalize(leftHospital) === normalize(rightHospital) && normalize(leftDepartment) === normalize(rightDepartment)
}

function productHint(card: TodayActionCard): string | null {
  const product = card.facts.products?.find((item) => item.name?.trim())?.name?.trim()
  if (product) return product
  const category = card.facts.product_categories?.find((item) => item.trim())?.trim()
  if (category) return category

  const projectText = normalize(card.facts.project_name)
  if (!projectText) return null
  const hint = PROJECT_CAPABILITY_HINTS.find((item) =>
    item.terms.some((term) => projectText.includes(normalize(term))),
  )
  return hint?.keyword ?? null
}

function StatusRow({
  icon,
  label,
  value,
  detail,
  ready,
}: {
  icon: ReactNode
  label: string
  value: string
  detail: string
  ready: boolean
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-3">
      <div className={`mt-0.5 rounded-lg p-1.5 ${ready ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'}`}>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[12px] font-medium text-slate-600">{label}</p>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${ready ? 'bg-teal-100 text-teal-800' : 'bg-amber-100 text-amber-800'}`}>
            {ready ? '已具备' : '待补充'}
          </span>
        </div>
        <p className="mt-1 text-[13px] font-medium text-slate-900">{value}</p>
        <p className="mt-0.5 text-[11px] leading-5 text-slate-500">{detail}</p>
      </div>
    </div>
  )
}

export function OpportunityExecutionCard({
  card,
  onProfileChanged,
}: {
  card: TodayActionCard
  onProfileChanged: () => Promise<void> | void
}) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [profile, setProfile] = useState<LocalCustomerProfile>(() => emptyLocalCustomerProfile())
  const [profileReady, setProfileReady] = useState(false)
  const [saving, setSaving] = useState<'target' | 'relationship' | 'capability' | null>(null)
  const [relationshipEditor, setRelationshipEditor] = useState(false)
  const [relationshipStrength, setRelationshipStrength] = useState<RelationshipStrength>('MEDIUM')
  const [capabilityEditor, setCapabilityEditor] = useState(false)
  const [capabilityKeyword, setCapabilityKeyword] = useState('')
  const [capabilityType, setCapabilityType] = useState<CapabilityType>('DIRECT_UNCONFIRMED')

  useEffect(() => {
    let active = true
    void loadCustomerProfile()
      .then((value) => {
        if (!active) return
        setProfile(value)
        setProfileReady(true)
      })
      .catch((cause) => {
        if (!active) return
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        setProfileReady(false)
      })
    return () => {
      active = false
    }
  }, [navigate])

  const explicitHospital = card.facts.hospital?.trim() || null
  const fallbackBuyerHospital = explicitHospital ? null : medicalInstitutionBuyer(card.facts.buyer_name)
  const hospital = explicitHospital ?? fallbackBuyerHospital
  const hospitalFromBuyer = Boolean(!explicitHospital && fallbackBuyerHospital)
  const department = card.facts.department?.trim() || null
  const contextTarget = card.customer_context.target_hospital ?? null
  const relationship = card.customer_context.hospital_relationship
  const capability = card.customer_context.matching_product_capabilities[0] ?? null
  const hint = productHint(card)

  useEffect(() => {
    if (!capabilityKeyword && hint) setCapabilityKeyword(hint)
  }, [capabilityKeyword, hint])

  const alreadyTargeted = useMemo(() => {
    if (contextTarget) return true
    if (!hospital) return false
    return profile.target_hospitals.some((item) =>
      sameScope(item.hospital, item.department, hospital, department),
    )
  }, [contextTarget, department, hospital, profile.target_hospitals])

  const persistProfile = async (
    nextProfile: LocalCustomerProfile,
    kind: 'target' | 'relationship' | 'capability',
    successMessage: string,
  ) => {
    setSaving(kind)
    try {
      const saved = await saveCustomerProfile(nextProfile)
      setProfile(saved)
      toast(successMessage, 'success')
      await onProfileChanged()
      return true
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return false
      }
      toast('资源保存失败，请稍后重试')
      return false
    } finally {
      setSaving(null)
    }
  }

  const addTargetHospital = async () => {
    if (!hospital || alreadyTargeted || saving) return
    await persistProfile(
      {
        ...profile,
        target_hospitals: [
          ...profile.target_hospitals,
          { hospital, department },
        ],
      },
      'target',
      department
        ? `已把 ${hospital} / ${department} 加入重点关注`
        : `已把 ${hospital} 加入重点关注`,
    )
  }

  const saveRelationship = async () => {
    if (!hospital || saving) return
    const existingIndex = profile.hospital_relationships.findIndex((item) =>
      sameExactScope(item.hospital, item.department, hospital, department),
    )
    const nextRelationships = [...profile.hospital_relationships]
    const nextRelationship = {
      hospital,
      department,
      relationship_strength: relationshipStrength,
    }
    if (existingIndex >= 0) nextRelationships[existingIndex] = nextRelationship
    else nextRelationships.push(nextRelationship)

    const saved = await persistProfile(
      { ...profile, hospital_relationships: nextRelationships },
      'relationship',
      `已确认 ${hospital} 的院内关系：${RELATIONSHIP_LABEL[relationshipStrength]}`,
    )
    if (saved) setRelationshipEditor(false)
  }

  const saveCapability = async () => {
    if (saving) return
    const keyword = capabilityKeyword.trim()
    if (!keyword || !isSpecificCapabilityKeyword(keyword)) {
      toast('请填写更具体的产品/服务关键词，例如“生化分析仪”“DR”“DSA”“病原微生物质谱”')
      return
    }
    const existingIndex = profile.product_capabilities.findIndex(
      (item) => normalize(item.keyword) === normalize(keyword),
    )
    const nextCapabilities = [...profile.product_capabilities]
    const nextCapability = { keyword, capability_type: capabilityType }
    if (existingIndex >= 0) nextCapabilities[existingIndex] = nextCapability
    else nextCapabilities.push(nextCapability)

    const saved = await persistProfile(
      { ...profile, product_capabilities: nextCapabilities },
      'capability',
      `已确认产品能力：${keyword} · ${CAPABILITY_LABEL[capabilityType]}`,
    )
    if (saved) setCapabilityEditor(false)
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4.5 w-4.5 text-teal-700" />
            <h3 className="text-[15px] font-semibold text-slate-900">这条商机的执行准备</h3>
          </div>
          <p className="mt-1 text-[12px] leading-5 text-slate-500">
            把“看到商机”直接接到你的经营动作。只有你确认过的关系和产品能力才会保存，并立即重新计算当前商机的个性化优先级。
          </p>
        </div>
        <Link
          to="/resources"
          className="self-start rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
        >
          管理全部资源
        </Link>
      </div>

      <div className="mt-3 grid gap-2 lg:grid-cols-3">
        <StatusRow
          icon={<Target className="h-4 w-4" />}
          label="目标医院"
          ready={alreadyTargeted}
          value={
            hospital
              ? alreadyTargeted
                ? `${hospital}${department ? ` / ${department}` : ''}`
                : '当前还未加入重点关注'
              : '公告未明确到具体医院'
          }
          detail={
            hospital
              ? alreadyTargeted
                ? '表示你想持续经营/监控，不代表已有院内关系。'
                : hospitalFromBuyer
                  ? '公告未单列医院字段，但采购单位名称明确包含医疗机构称谓；仍只作为重点关注，不代表已有关系。'
                  : '加入后可在“目标”页持续查看该医院的已核验机会。'
              : '不会把普通采购单位、代理机构或公司名称猜成目标医院。'
          }
        />
        <StatusRow
          icon={<Users className="h-4 w-4" />}
          label="院内关系"
          ready={Boolean(relationship)}
          value={
            relationship
              ? `${RELATIONSHIP_LABEL[relationship.relationship_strength]}${relationship.department ? ` · ${relationship.department}` : ''}`
              : '尚未确认真实院内关系'
          }
          detail={relationship ? '只使用你自己确认过的关系参与个性化评分。' : '公开联系人不会被自动当成你的私人关系。'}
        />
        <StatusRow
          icon={<PackageSearch className="h-4 w-4" />}
          label="产品 / 执行能力"
          ready={Boolean(capability)}
          value={capability ? `${capability.category} · ${CAPABILITY_LABEL[capability.capability_type]}` : '暂无匹配的自有产品能力'}
          detail={capability ? '该能力会参与当前商机的个性化可执行性判断。' : hint ? `公告产品/项目提示：${hint}。确认你能做后再录入资源。` : '当前公开事实不足以安全替你自动创建产品能力。'}
        />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {hospital && !alreadyTargeted ? (
          <button
            type="button"
            disabled={!profileReady || Boolean(saving)}
            onClick={() => void addTargetHospital()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 px-3 py-2 text-[12px] font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Building2 className="h-3.5 w-3.5" />
            {saving === 'target' ? '正在加入…' : '一键加入目标医院'}
          </button>
        ) : null}
        {alreadyTargeted ? (
          <Link
            to="/targets"
            className="inline-flex items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-[12px] font-medium text-teal-800 hover:bg-teal-100"
          >
            <Target className="h-3.5 w-3.5" /> 查看目标医院
          </Link>
        ) : null}
        {hospital && !relationship ? (
          <button
            type="button"
            disabled={!profileReady || Boolean(saving)}
            onClick={() => setRelationshipEditor((value) => !value)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50"
          >
            <Users className="h-3.5 w-3.5" /> 记录真实院内关系
          </button>
        ) : null}
        {!capability ? (
          <button
            type="button"
            disabled={!profileReady || Boolean(saving)}
            onClick={() => setCapabilityEditor((value) => !value)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-[12px] font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-50"
          >
            <PackageSearch className="h-3.5 w-3.5" /> 补充产品能力
          </button>
        ) : null}
      </div>

      {relationshipEditor && hospital && !relationship ? (
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[12px] font-semibold text-amber-950">确认你真实掌握的医院关系</p>
              <p className="mt-1 text-[11px] leading-5 text-amber-800">
                {hospital}{department ? ` / ${department}` : ''}。这里只记录你自己确认过的关系，不读取公告联系人进行推断。
              </p>
            </div>
            <button type="button" onClick={() => setRelationshipEditor(false)} className="rounded p-1 text-amber-700 hover:bg-amber-100">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <select
              value={relationshipStrength}
              onChange={(event) => setRelationshipStrength(event.target.value as RelationshipStrength)}
              className="min-w-0 flex-1 rounded-lg border border-amber-200 bg-white px-3 py-2 text-[12px] text-slate-700 outline-none focus:border-amber-500"
            >
              {RELATIONSHIP_OPTIONS.map((value) => (
                <option key={value} value={value}>{RELATIONSHIP_LABEL[value]}</option>
              ))}
            </select>
            <button
              type="button"
              disabled={Boolean(saving)}
              onClick={() => void saveRelationship()}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-amber-700 px-3 py-2 text-[12px] font-medium text-white hover:bg-amber-800 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {saving === 'relationship' ? '保存中…' : '确认并保存关系'}
            </button>
          </div>
        </div>
      ) : null}

      {capabilityEditor && !capability ? (
        <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50/60 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-[12px] font-semibold text-indigo-950">确认你能执行的产品 / 服务能力</p>
              <p className="mt-1 text-[11px] leading-5 text-indigo-800">
                {hint ? `下面关键词仅由公告产品字段或标题中的确定性医疗术语提示为“${hint}”，不是系统认定你有这项资源。` : '请填写你实际能够执行的具体产品或服务。'}
              </p>
            </div>
            <button type="button" onClick={() => setCapabilityEditor(false)} className="rounded p-1 text-indigo-700 hover:bg-indigo-100">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_220px_auto]">
            <input
              value={capabilityKeyword}
              onChange={(event) => setCapabilityKeyword(event.target.value)}
              placeholder="具体产品 / 服务关键词"
              className="min-w-0 rounded-lg border border-indigo-200 bg-white px-3 py-2 text-[12px] text-slate-700 outline-none focus:border-indigo-500"
            />
            <select
              value={capabilityType}
              onChange={(event) => setCapabilityType(event.target.value as CapabilityType)}
              className="rounded-lg border border-indigo-200 bg-white px-3 py-2 text-[12px] text-slate-700 outline-none focus:border-indigo-500"
            >
              {CAPABILITY_OPTIONS.map((value) => (
                <option key={value} value={value}>{CAPABILITY_LABEL[value]}</option>
              ))}
            </select>
            <button
              type="button"
              disabled={Boolean(saving)}
              onClick={() => void saveCapability()}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-indigo-700 px-3 py-2 text-[12px] font-medium text-white hover:bg-indigo-800 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {saving === 'capability' ? '保存中…' : '确认并保存能力'}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
