export function discoveryAccountToken(username: string): string
export function activateDiscoveryWorkspaceForAccount(username: string): Promise<string>
export function clearActiveDiscoveryWorkspaceAccount(): Promise<void>
