import { Building2, ExternalLink, Radar, ShieldCheck, Target } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import {
  emptyLocalCustomerProfile,
  type LocalCustomerProfile,
  type LocalHospitalRelationship,
  type LocalTargetHospital,
} from '@/services/localCustomerProfile'
import { loadCustomerProfile } from '@/services/profileApi'
import {
  getTargetHospitalOpportunityPool,
  type TargetHospitalOpportunity,
} from '@/services/targetHospitalOpportunityApi'
import type { PriorityScoreScope, RelationshipStrength, TodayActionCard } from '@/types'
import { formatBudget, formatDateOnly, formatDateTime } from '@/utils/format'
import { RELATIONSHIP_LABEL } from '@/utils/labels'

const RELATIONSHIP_WEIGHT: Record<RelationshipStrength, number> = {
  STRONG: 5,
  MEDIUM: 4,
  HISTORICAL: 3,
  WEAK: 2,
  UNKNOWN: 1,
  NONE: 0,
}

function normalize(value: string | null | undefined): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s\-_—–·,，。；;：:（）()【】\[\]]+/g, '')
}

function fuzzySame(left: string | null | undefined, right: string | null | undefined): boolean {
  const a = normalize(left)
  const b = normalize(right)
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)))
}

function fromTodayCard(card: TodayActionCard): TargetHospitalOpportunity {
  return {
    opportunity_id: card.opportunity_id,
    rank: card.rank,
    hospital: card.facts.hospital,
    buyer_name: card.facts.buyer_name ?? null,
    department: card.facts.department,
    project_name: card.facts.project_name,
    priority_score: card.priority.score,
    score_scope: card.priority.score_scope ?? 'PUBLIC',
    budget_cny: card.facts.budget,
    registration_deadline: card.facts.registration_deadline,
    registration_deadline_date: card.facts.registration_deadline_date ?? null,
    bid_deadline: card.facts.bid_deadline,
  }
}

function targetMatchesOpportunity(
  target: LocalTargetHospital,
  card: TargetHospitalOpportunity,
): boolean {
  const hospital = card.hospital || card.buyer_name || null
  if (!fuzzySame(target.hospital, hospital)) return false
  if (!target.department) return true
  return fuzzySame(target.department, card.department)
}

function relationshipMatchesTarget(target: LocalTargetHospital, relation: LocalHospitalRelationship): boolean {
  if (!fuzzySame(target.hospital, relation.hospital)) return false
  if (!target.department || !relation.department) return true
  return fuzzySame(target.department, relation.department)
}

function bestRelationship(
  target: LocalTargetHospital,
  relationships: LocalHospitalRelationship[],
): LocalHospitalRelationship | null {
  return relationships
    .filter((relation) => relationshipMatchesTarget(target, relation))
    .sort(
      (left, right) =>
        RELATIONSHIP_WEIGHT[right.relationship_strength] -
        RELATIONSHIP_WEIGHT[left.relationship_strength],
    )[0] ?? null
}

function targetKey(target: LocalTargetHospital): string {
  return `${normalize(target.hospital)}::${normalize(target.department)}`
}

function actionableDeadline(card: TargetHospitalOpportunity): string | null {
  if (card.registration_deadline) {
    const value = formatDateTime(card.registration_deadline)
    if (value) return `报名/资料截止 ${value}`
  }
  if (card.registration_deadline_date) {
    const value = formatDateOnly(card.registration_deadline_date)
    if (value) return `报名/资料截止 ${value}（未公布具体时间）`
  }
  if (card.bid_deadline) {
    const value = formatDateTime(card.bid_deadline)
    if (value) return `投标/响应截止 ${value}`
  }
  return null
}

function scoreText(score: number, scope: PriorityScoreScope): string {
  const label = scope === 'PERSONALIZED' ? '个性化分' : '公开分'
  const denominator = scope === 'PERSONALIZED' ? 100 : 60
  return `${score}/${denominator} ${label}`
}

export function TargetHospitalsPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [profile, setProfile] = useState<LocalCustomerProfile>(() => emptyLocalCustomerProfile())
  const [opportunityPool, setOpportunityPool] = useState<TargetHospitalOpportunity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)

    const opportunityRequest = isApiMode
      ? getTargetHospitalOpportunityPool()
      : todayActionsService.getTodayActions().then((actions) =>
          (actions.opportunity_pool ?? actions.cards).map(fromTodayCard),
        )

    Promise.all([loadCustomerProfile(), opportunityRequest])
      .then(([nextProfile, nextPool]) => {
        if (!active) return
        setProfile(nextProfile)
        setOpportunityPool(nextPool)
        setError(false)
      })
      .catch((cause) => {
        if (!active) return
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        setError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [navigate])

  const targetRows = useMemo(() => {
    const uniqueTargets = new Map<string, LocalTargetHospital>()
    for (const target of profile.target_hospitals) {
      if (!target.hospital.trim()) continue
      const key = targetKey(target)
      if (!uniqueTargets.has(key)) uniqueTargets.set(key, target)
    }
    return [...uniqueTargets.values()].map((target) => {
      const opportunities = opportunityPool
        .filter((card) => targetMatchesOpportunity(target, card))
        .sort((left, right) => right.priority_score - left.priority_score || left.rank - right.rank)
      return {
        target,
        relationship: bestRelationship(target, profile.hospital_relationships),
        opportunities,
      }
    })
  }, [opportunityPool, profile.hospital_relationships, profile.target_hospitals])

  const metrics = useMemo(() => ({
    total: targetRows.length,
    withOpportunity: targetRows.filter((row) => row.opportunities.length > 0).length,
    withRelationship: targetRows.filter((row) => row.relationship).length,
    withoutRelationship: targetRows.filter((row) => !row.relationship).length,
  }), [targetRows])

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">正在整理目标医院经营视图…</div>
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-rose-100 bg-white p-6">
        <h2 className="font-semibold text-slate-900">目标医院经营视图暂时无法读取</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">系统不会用浏览器旧数据代替当前账号数据。请检查网络或私有数据库状态后重试。</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-4 rounded-lg bg-teal-700 px-4 py-2 text-sm text-white">重试</button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5 text-teal-700" />
              <h2 className="text-lg font-semibold text-slate-900">目标医院经营视图</h2>
            </div>
            <p className="mt-1 max-w-3xl text-[13px] leading-6 text-slate-500">
              管理“我想进入哪家医院”，即使当前完全没有院内关系也可以持续关注。目标医院本身不会增加医院关系分。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/resources" className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12px] font-medium text-slate-700 hover:bg-slate-50">
              <ShieldCheck className="h-3.5 w-3.5" /> 管理目标与关系
            </Link>
            <Link to="/radar" className="inline-flex items-center gap-1.5 rounded-lg bg-teal-700 px-3 py-2 text-[12px] font-medium text-white hover:bg-teal-800">
              <Radar className="h-3.5 w-3.5" /> 配置公开渠道
            </Link>
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2.5 text-[12px] leading-5 text-amber-900">
          目标医院名称不会自动推导官网地址。需要持续扫描时，请在 AI 雷达中显式添加并确认官方公开栏目，避免猜错来源。
        </div>
        {isApiMode ? (
          <div className="mt-2 rounded-xl border border-teal-100 bg-teal-50/70 px-3 py-2 text-[11px] leading-5 text-teal-900">
            当前按完整个性化商机池匹配目标医院，不受“今日 Top5”截断影响。
          </div>
        ) : null}
      </section>

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['目标医院', metrics.total],
          ['当前有机会', metrics.withOpportunity],
          ['已有关系', metrics.withRelationship],
          ['无关系待开发', metrics.withoutRelationship],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <p className="text-[11px] text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </section>

      {targetRows.length === 0 ? (
        <section className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center">
          <Building2 className="mx-auto h-8 w-8 text-slate-300" />
          <h3 className="mt-3 text-[15px] font-semibold text-slate-800">还没有目标医院</h3>
          <p className="mx-auto mt-1 max-w-xl text-[12px] leading-5 text-slate-500">可以先把想开发、想长期盯住的医院加入目标列表，不需要先有院内关系。</p>
          <Link to="/resources" className="mt-4 inline-flex rounded-lg bg-teal-700 px-4 py-2 text-[13px] font-medium text-white">添加目标医院</Link>
        </section>
      ) : (
        <div className="space-y-3">
          {targetRows.map(({ target, relationship, opportunities }) => (
            <section key={targetKey(target)} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[16px] font-semibold text-slate-900">{target.hospital}</h3>
                    <span className="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-800">重点关注</span>
                  </div>
                  <p className="mt-1 text-[12px] text-slate-500">{target.department ? `重点科室：${target.department}` : '关注范围：全院'}</p>
                </div>
                <div className="text-left sm:text-right">
                  {relationship ? (
                    <>
                      <p className="text-[12px] font-medium text-slate-700">院内关系：{RELATIONSHIP_LABEL[relationship.relationship_strength]}</p>
                      <p className="mt-0.5 text-[11px] text-slate-400">{relationship.department ? `关系科室：${relationship.department}` : '医院级关系'}</p>
                    </>
                  ) : (
                    <p className="text-[12px] font-medium text-amber-700">院内关系：尚未确认</p>
                  )}
                </div>
              </div>

              <div className="mt-3 border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12px] font-medium text-slate-700">当前已核验可行动机会：{opportunities.length} 条</p>
                  {opportunities.length > 3 ? <span className="text-[11px] text-slate-400">显示优先级最高 3 条</span> : null}
                </div>

                {opportunities.length === 0 ? (
                  <div className="mt-2 rounded-xl bg-slate-50 px-3 py-3 text-[12px] leading-5 text-slate-500">
                    当前已核验公开商机池中暂无可行动机会。继续关注，不代表其他尚未覆盖的公开来源一定没有信息。
                  </div>
                ) : (
                  <div className="mt-2 space-y-2">
                    {opportunities.slice(0, 3).map((card) => {
                      const budget = formatBudget(card.budget_cny)
                      const deadline = actionableDeadline(card)
                      return (
                        <Link
                          key={card.opportunity_id}
                          to={`/opportunity/${encodeURIComponent(card.opportunity_id)}`}
                          className="block rounded-xl border border-slate-100 bg-slate-50 p-3 hover:border-teal-200 hover:bg-teal-50/40"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[13px] font-medium leading-5 text-slate-800">{card.project_name ?? '未命名商机'}</p>
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                                <span>{scoreText(card.priority_score, card.score_scope)}</span>
                                {budget ? <span>预算 {budget}</span> : null}
                                {deadline ? <span>{deadline}</span> : null}
                              </div>
                            </div>
                            <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                          </div>
                        </Link>
                      )
                    })}
                  </div>
                )}
              </div>
            </section>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => {
          toast('目标医院只表示经营意图；公开渠道需要在 AI 雷达中单独确认。', 'success')
          navigate('/radar')
        }}
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-[12px] font-medium text-slate-700 shadow-sm hover:bg-slate-50"
      >
        下一步：为重点医院配置可核验的官方公开渠道
      </button>
    </div>
  )
}
