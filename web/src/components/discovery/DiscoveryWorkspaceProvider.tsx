import {
  createContext,
  useContext,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react'
import {
  loadDiscoveryWorkspace,
  type DiscoveryStorageStatus,
  type DiscoveryWorkspace,
} from '@/services/discoveryRadarStore'

interface DiscoveryWorkspaceContextValue {
  workspace: DiscoveryWorkspace
  setWorkspace: Dispatch<SetStateAction<DiscoveryWorkspace>>
  storageReady: boolean
  setStorageReady: Dispatch<SetStateAction<boolean>>
  storageStatus: DiscoveryStorageStatus | null
  setStorageStatus: Dispatch<SetStateAction<DiscoveryStorageStatus | null>>
}

const DiscoveryWorkspaceContext = createContext<DiscoveryWorkspaceContextValue | null>(null)

export function DiscoveryWorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspace, setWorkspace] = useState(() => loadDiscoveryWorkspace())
  const [storageReady, setStorageReady] = useState(false)
  const [storageStatus, setStorageStatus] = useState<DiscoveryStorageStatus | null>(null)

  const value = useMemo<DiscoveryWorkspaceContextValue>(() => ({
    workspace,
    setWorkspace,
    storageReady,
    setStorageReady,
    storageStatus,
    setStorageStatus,
  }), [storageReady, storageStatus, workspace])

  return <DiscoveryWorkspaceContext.Provider value={value}>{children}</DiscoveryWorkspaceContext.Provider>
}

export function useDiscoveryWorkspace() {
  const context = useContext(DiscoveryWorkspaceContext)
  if (!context) throw new Error('DiscoveryWorkspaceProvider is required')
  return context
}
