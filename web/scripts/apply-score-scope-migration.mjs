import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(process.cwd())

function replaceExactlyOnce(relativePath, before, after) {
  const path = resolve(root, relativePath)
  const source = readFileSync(path, 'utf8')
  const first = source.indexOf(before)
  if (first < 0) throw new Error(`MIGRATION_PATTERN_MISSING:${relativePath}`)
  if (source.indexOf(before, first + before.length) >= 0) {
    throw new Error(`MIGRATION_PATTERN_AMBIGUOUS:${relativePath}`)
  }
  writeFileSync(path, source.slice(0, first) + after + source.slice(first + before.length), 'utf8')
}

replaceExactlyOnce(
  'src/services/ApiTodayActionsService.ts',
  `    priority: {\n      score: card.priority.score,\n      components: {`,
  `    priority: {\n      score: card.priority.score,\n      score_scope:\n        card.priority.score_scope ??\n        (card.priority.score_type === 'BUSINESS_PRIORITY_PERSONALIZED_V2' ? 'PERSONALIZED' : 'PUBLIC'),\n      components: {`,
)

replaceExactlyOnce(
  'src/services/StaticSnapshotTodayActionsService.ts',
  `    priority: {\n      score: card.priority.score,\n      components: {`,
  `    priority: {\n      score: card.priority.score,\n      score_scope: 'PUBLIC',\n      components: {`,
)

replaceExactlyOnce(
  'src/services/localCustomerProfile.ts',
  `      priority: {\n        score: Math.min(100, publicBase + privatePoints),\n        components: {`,
  `      priority: {\n        score: Math.min(100, publicBase + privatePoints),\n        score_scope: 'PERSONALIZED',\n        components: {`,
)

replaceExactlyOnce(
  'src/services/verifiedOpportunityPool.ts',
  `    priority: {\n      score: card.priority.score,\n      components: {`,
  `    priority: {\n      score: card.priority.score,\n      score_scope: 'PUBLIC',\n      components: {`,
)

console.log('Score scope migration applied')
