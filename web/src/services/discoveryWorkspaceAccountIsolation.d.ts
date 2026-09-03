export function discoveryAccountToken(username: string): string
export function discoveryWorkspaceIsAccountScoped(): boolean
export function discoveryWorkspaceStorageKey(): string
export function discoveryWorkspaceDbKey(): string
export function activateDiscoveryWorkspaceForAccount(username: string): Promise<string>
export function clearActiveDiscoveryWorkspaceAccount(): Promise<void>
