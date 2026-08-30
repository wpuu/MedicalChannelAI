const env = (import.meta as ImportMeta & {
  env?: Record<string, string | undefined>
}).env

export type DemoDatasetMode = 'synthetic' | 'verified'

const raw = env?.VITE_DEMO_DATASET?.trim()?.toLowerCase() ?? ''

/**
 * Static Demo dataset selector.
 *
 * synthetic: every opportunity/customer field is fictional.
 * verified: public procurement facts come from a frozen official-source snapshot;
 *           customer relationship/product capability remains an explicit demo profile.
 */
export const demoDatasetMode: DemoDatasetMode = raw === 'verified' ? 'verified' : 'synthetic'
export const isVerifiedPublicDemo = demoDatasetMode === 'verified'
