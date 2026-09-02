import { DiscoveryContinuationDashboard } from '@/components/discovery/DiscoveryContinuationDashboard'
import { DiscoveryRadarPage } from '@/pages/DiscoveryRadarPage'

export function DiscoveryRadarRoute() {
  return (
    <div className="space-y-4">
      <DiscoveryRadarPage />
      <DiscoveryContinuationDashboard />
    </div>
  )
}
