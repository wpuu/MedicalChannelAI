import {
  clearLocalCustomerProfile,
  emptyLocalCustomerProfile,
  loadLocalCustomerProfile,
  type LocalCustomerProfile,
} from './localCustomerProfile'

function normalize(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase().replace(/[\s（）()、，,·.\-_/]+/g, '')
}

export function hasProfileData(profile: LocalCustomerProfile): boolean {
  return Boolean(
    profile.product_capabilities.length ||
    profile.hospital_relationships.length ||
    profile.can_find_manufacturer !== null ||
    profile.can_partner_channel !== null ||
    profile.can_handle_lease !== null,
  )
}

export function loadImportableLocalProfile(): LocalCustomerProfile | null {
  const profile = loadLocalCustomerProfile()
  return hasProfileData(profile) ? profile : null
}

export function mergeLocalProfileIntoAccount(
  account: LocalCustomerProfile,
  local: LocalCustomerProfile,
): LocalCustomerProfile {
  const productKeys = new Set(
    account.product_capabilities.map((item) => normalize(item.keyword)),
  )
  const product_capabilities = [...account.product_capabilities]
  for (const item of local.product_capabilities) {
    const key = normalize(item.keyword)
    if (!key || productKeys.has(key)) continue
    productKeys.add(key)
    product_capabilities.push({ ...item })
    if (product_capabilities.length >= 50) break
  }

  const relationshipKeys = new Set(
    account.hospital_relationships.map(
      (item) => `${normalize(item.hospital)}|${normalize(item.department)}`,
    ),
  )
  const hospital_relationships = [...account.hospital_relationships]
  for (const item of local.hospital_relationships) {
    const key = `${normalize(item.hospital)}|${normalize(item.department)}`
    if (!normalize(item.hospital) || relationshipKeys.has(key)) continue
    relationshipKeys.add(key)
    hospital_relationships.push({ ...item })
    if (hospital_relationships.length >= 100) break
  }

  return {
    product_capabilities,
    hospital_relationships,
    // Existing account values win. Local data only fills fields the account has
    // never answered, so an old browser cannot silently overwrite newer choices.
    can_find_manufacturer:
      account.can_find_manufacturer ?? local.can_find_manufacturer,
    can_partner_channel:
      account.can_partner_channel ?? local.can_partner_channel,
    can_handle_lease:
      account.can_handle_lease ?? local.can_handle_lease,
    updated_at: account.updated_at,
  }
}

export function clearImportedLocalProfile(): LocalCustomerProfile {
  clearLocalCustomerProfile()
  return emptyLocalCustomerProfile()
}
