import { LEGAL_LAST_UPDATED } from "@/routes/pages/LegalPageLayout"

export const POLICY_ACKNOWLEDGMENT_KEY = "aegis:policy-acknowledgment"

export function hasAcknowledgedPolicies() {
  try {
    return (
      localStorage.getItem(POLICY_ACKNOWLEDGMENT_KEY) === LEGAL_LAST_UPDATED
    )
  } catch {
    return false
  }
}
