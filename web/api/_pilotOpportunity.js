import { waitUntil } from '@vercel/functions'
import {
  loadPrivateProfileForUser,
  minimalPrivateContextFromProfile,
  privatePriorityPoints,
} from './_privateProfileContext.js'
import { materializeVerifiedSnapshot } from './_publicIntelligenceDb.js'
import { runtimeRefreshSnapshotPool } from './_runtimeOpportunityTime.js'

const PRIVATE_COMPONENT_CODES = new Set([
  'PRODUCT_EXECUTION_CAPABILITY',
  'RELATIONSHIP',
  'EXECUTION_FLEXIBILITY',
])
const MATERIALIZED_SNAPSHOT_KEYS_MAX = 20
const materializedSnapshotKeys = new Set()
const materializingSnapshotKeys = new Set()

export function snapshotOpportunityPool(snapshot) {
  if (Array.isArray(snapshot?.opportunity_pool) && snapshot.opportunity_pool.length) {
    return snapshot.opportunity_pool
  }
  return Array.isArray(snapshot?.cards) ? snapshot.cards : []
}

export function runtimeSnapshotOpportunityPool(snapshot, now = Date.now()) {
  return runtimeRefreshSnapshotPool(snapshotOpportunityPool(snapshot), now)
}

export function findVerifiedSnapshotCard(snapshot, opportunityId) {
  const card = runtimeSnapshotOpportunityPool(snapshot).find(
    (item) => item?.opportunity_id === opportunityId,
  )
  return card?.facts?.verification_status === 'VERIFIED' ? card : null
}

function rememberMaterializedSnapshot(key) {
  materializedSnapshotKeys.add(key)
  if (materializedSnapshotKeys.size > MATERIALIZED_SNAPSHOT_KEYS_MAX) {
    const oldest = materializedSnapshotKeys.values().next().value
    if (oldest) materializedSnapshotKeys.delete(oldest)
  }
}

async function materializePublicSnapshotTask(snapshot, key) {
  try {
    await materializeVerifiedSnapshot(snapshot)
    rememberMaterializedSnapshot(key)
  } catch (error) {
    // The verified snapshot remains the serving authority. Public history is a
    // durable side-store and retries on a later request rather than breaking Today.
    console.warn('public intelligence materialization deferred', {
      snapshot_as_of: key,
      error: error instanceof Error ? error.message : 'UNKNOWN',
    })
  } finally {
    materializingSnapshotKeys.delete(key)
  }
}

async function materializePublicSnapshotBestEffort(snapshot) {
  const key = typeof snapshot?.snapshot_as_of === 'string' ? snapshot.snapshot_as_of.trim() : ''
  if (!key || materializedSnapshotKeys.has(key) || materializingSnapshotKeys.has(key)) return
  materializingSnapshotKeys.add(key)
  const task = materializePublicSnapshotTask(snapshot, key)

  if (process.env.VERCEL) {
    try {
      waitUntil(task)
      return
    } catch (error) {
      console.warn('public intelligence background scheduling unavailable; using request path', {
        snapshot_as_of: key,
        error: error instanceof Error ? error.message : 'UNKNOWN',
      })
    }
  }
  await task
}

function publicCustomerContext(privateContext) {
  const target = privateContext.target_hospital
  const relation = privateContext.hospital_relationship
  return {
    context_type: 'CUSTOMER_PRIVATE_FACTS',
    business_role: null,
    target_hospital: target
      ? {
          hospital_name: target.hospital,
          department: target.department,
          watched_by_customer: true,
          updated_at: target.updated_at,
        }
      : null,
    hospital_relationship: relation
      ? {
          hospital_name: relation.hospital,
          department: relation.department,
          relationship_strength: relation.relationship_strength,
          owner: null,
          confirmed_by_customer: true,
          last_confirmed_at: relation.last_confirmed_at,
        }
      : null,
    matching_product_capabilities: privateContext.matching_product_capabilities.map((item) => ({
      category: item.category,
      subcategory: item.subcategory,
      matched_taxonomy_ids: [],
      brands: [...item.brands],
      capability_type: item.capability_type,
    })),
    partnering_policy: {
      can_seek_temporary_manufacturer: privateContext.partnering_policy.can_find_manufacturer,
      can_cooperate_with_channel_partner: privateContext.partnering_policy.can_partner_channel,
      can_do_rental_projects: privateContext.partnering_policy.can_handle_lease,
    },
  }
}

function privateComponentValue(code, points) {
  if (code === 'PRODUCT_EXECUTION_CAPABILITY') return points.capability
  if (code === 'RELATIONSHIP') return points.relationship
  if (code === 'EXECUTION_FLEXIBILITY') return points.flexibility
  return null
}

function personalizePriority(priority, points) {
  const components = Array.isArray(priority?.components)
    ? priority.components.map((component) => {
        const value = privateComponentValue(component.code, points)
        if (value === null) return { ...component }
        const label = component.code === 'PRODUCT_EXECUTION_CAPABILITY'
          ? '账号私有产品/服务能力（用户主动填写）'
          : component.code === 'RELATIONSHIP'
            ? '账号私有医院关系（用户主动填写）'
            : '账号私有合作能力（用户主动填写）'
        return {
          ...component,
          points: Math.max(0, Math.min(component.max_points, value)),
          basis: label,
          profile_paths: [`private_profile.${component.code.toLowerCase()}`],
        }
      })
    : []

  const oldPrivate = (priority?.components || [])
    .filter((component) => PRIVATE_COMPONENT_CODES.has(component.code))
    .reduce((sum, component) => sum + Number(component.points || 0), 0)
  const privateTotal = points.capability + points.relationship + points.flexibility
  const publicBase = Math.max(0, Number(priority?.score || 0) - oldPrivate)

  return {
    ...priority,
    score: Math.min(100, publicBase + privateTotal),
    score_type: 'BUSINESS_PRIORITY_PERSONALIZED_V2',
    score_scope: 'PERSONALIZED',
    components,
    warnings: Array.from(new Set([
      ...(Array.isArray(priority?.warnings) ? priority.warnings : []),
      'PRIVATE_PROFILE_SELF_REPORTED',
    ])),
  }
}

export function personalizeSnapshotCardWithProfile(card, profile) {
  const privateResult = minimalPrivateContextFromProfile(profile, card.facts)
  const points = privatePriorityPoints(privateResult.context, card.facts)
  const privateTotal = points.capability + points.relationship + points.flexibility
  const hasTargetFocus = Boolean(privateResult.context.target_hospital)
  return {
    ...card,
    customer_context: publicCustomerContext(privateResult.context),
    priority: personalizePriority(card.priority, points),
    // A target hospital is a valid personalization match for filtering/attention,
    // but intentionally does not inflate the relationship or total priority score.
    match_status: privateTotal > 0 || hasTargetFocus ? 'MATCHED_PERSONALIZED' : 'MATCHED_CANDIDATE',
  }
}

export async function personalizedOpportunityPoolForUser(user, snapshot) {
  await materializePublicSnapshotBestEffort(snapshot)
  const profile = await loadPrivateProfileForUser(user)
  return runtimeSnapshotOpportunityPool(snapshot)
    .filter((card) => card?.facts?.verification_status === 'VERIFIED')
    .map((card) => personalizeSnapshotCardWithProfile(card, profile))
    .sort((a, b) => Number(b.priority?.score || 0) - Number(a.priority?.score || 0) || Number(a.rank || 0) - Number(b.rank || 0))
    .map((card, index) => ({ ...card, rank: index + 1 }))
}
