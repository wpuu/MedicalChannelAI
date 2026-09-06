import { publicOpenMode } from './publicOpenMode'

const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

export type DemoDatasetMode = 'synthetic' | 'verified'

const raw = env?.VITE_DEMO_DATASET?.trim()?.toLowerCase() ?? ''

/**
 * Static trial dataset selector.
 *
 * synthetic: every opportunity/customer field is fictional and used only for UI-flow testing.
 * verified: procurement facts come from the evidence-pipeline public snapshot;
 *           customer relationship/product capability remains empty until real customer data is supplied.
 */
export const demoDatasetMode: DemoDatasetMode = publicOpenMode || raw === 'verified' ? 'verified' : 'synthetic'
export const isVerifiedPublicDemo = demoDatasetMode === 'verified'
