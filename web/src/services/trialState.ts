const VERIFIED_TRIAL_STORAGE_KEYS = [
  'medopp.pipeline-followups.v1',
  'medopp.grounded-ai-decisions.v1',
]

export function resetVerifiedTrialState(): void {
  try {
    for (const key of VERIFIED_TRIAL_STORAGE_KEYS) {
      localStorage.removeItem(key)
    }
  } catch {
    // Trial reset should still navigate/reload even when browser storage is unavailable.
  }
}
