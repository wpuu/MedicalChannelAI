import { DiscoveryContinuationDashboard } from '@/components/discovery/DiscoveryContinuationDashboard'
import { DiscoveryWorkspaceProvider } from '@/components/discovery/DiscoveryWorkspaceProvider'
import { DiscoveryRadarPage } from '@/pages/DiscoveryRadarPage'

export function DiscoveryRadarRoute() {
  return (
    <DiscoveryWorkspaceProvider>
      <div className="space-y-4">
        <DiscoveryRadarPage />
        <DiscoveryContinuationDashboard />
      </div>
    </DiscoveryWorkspaceProvider>
  )
}
