import type { CustomerContext } from '@/types'

export function hasUserCustomerContext(context: CustomerContext): boolean {
  if (context.hospital_relationship) return true
  if (context.matching_product_capabilities.length > 0) return true
  return Object.values(context.partnering_policy).some((value) => typeof value === 'boolean')
}
