export function discoveryAccountToken(accountScope: string): string
export function discoveryWorkspaceIsAccountScoped(): boolean
export function discoveryWorkspaceStorageKey(): string
export function discoveryWorkspaceDbKey(): string
export function activateDiscoveryWorkspaceForAccount(accountScope: string): Promise<string>
export function clearActiveDiscoveryWorkspaceAccount(): Promise<void>
