import { useState } from "react"
import { ArrowLeft, FileText, ShieldCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  hasAcknowledgedPolicies,
  POLICY_ACKNOWLEDGMENT_KEY,
} from "@/lib/policy-acknowledgment"
import { LEGAL_LAST_UPDATED } from "@/routes/pages/LegalPageLayout"
import { PrivacyPolicyPage } from "@/routes/pages/PrivacyPolicyPage"
import { TermsOfUsePage } from "@/routes/pages/TermsOfUsePage"
import "@/routes/pages/login-legal-policies.css"
import "./policy-welcome.css"

/** Browser-local acknowledgment shown over the sign-in interface. */
export function PolicyWelcome({
  open = false,
  onAccepted,
  onCancel,
  cancelLabel = "Back to sign in",
}: {
  open?: boolean
  onAccepted?: () => void
  onCancel?: () => void
  cancelLabel?: string
}) {
  const [acknowledged, setAcknowledged] = useState(hasAcknowledgedPolicies)
  const [checked, setChecked] = useState(false)
  const [document, setDocument] = useState<"terms" | "privacy" | null>(null)

  function continueToSite() {
    if (!checked) return
    try {
      localStorage.setItem(POLICY_ACKNOWLEDGMENT_KEY, LEGAL_LAST_UPDATED)
    } catch {
      // Storage can be unavailable in private or restricted browser contexts.
    }
    setAcknowledged(true)
    onAccepted?.()
  }

  if (!open || acknowledged) return null

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && document) setDocument(null)
      }}
    >
      <DialogContent
        className={
          document
            ? "login-policy-dialog policy-welcome-document"
            : "policy-welcome"
        }
        showCloseButton={false}
        onPointerDownOutside={(event) => event.preventDefault()}
        onEscapeKeyDown={(event) => {
          event.preventDefault()
          if (document) setDocument(null)
        }}
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        {document ? (
          <>
            <button
              type="button"
              className="policy-welcome-back"
              onClick={() => setDocument(null)}
            >
              <ArrowLeft aria-hidden="true" /> Back to policies
            </button>
            {document === "terms" ? (
              <TermsOfUsePage
                presentation="dialog"
                closeLabel="Back to policies"
              />
            ) : (
              <PrivacyPolicyPage
                presentation="dialog"
                closeLabel="Back to policies"
              />
            )}
          </>
        ) : (
          <>
            <div className="policy-welcome-seal">
              <ShieldCheck aria-hidden="true" />
            </div>
            <p className="policy-welcome-eyebrow">
              AEGIS · His Care Christian Institute
            </p>
            <DialogTitle>Before you begin</DialogTitle>
            <DialogDescription>
              Welcome to your school community. Please review how AEGIS works
              and how the school handles your information before continuing.
            </DialogDescription>
            <div className="policy-welcome-links">
              <button type="button" onClick={() => setDocument("terms")}>
                <FileText aria-hidden="true" />
                <span>
                  <strong>Terms of Use</strong>
                  <small>Using your school portal responsibly</small>
                </span>
                <span aria-hidden="true">→</span>
              </button>
              <button type="button" onClick={() => setDocument("privacy")}>
                <ShieldCheck aria-hidden="true" />
                <span>
                  <strong>Privacy Policy</strong>
                  <small>How your information is handled</small>
                </span>
                <span aria-hidden="true">→</span>
              </button>
            </div>
            <label className="policy-welcome-check">
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => setChecked(event.target.checked)}
              />
              <span>
                I agree to the Terms of Use and acknowledge the Privacy Policy.
              </span>
            </label>
            <Button
              className="policy-welcome-continue"
              disabled={!checked}
              onClick={continueToSite}
            >
              Agree and continue
            </Button>
            {onCancel ? (
              <Button variant="ghost" onClick={onCancel}>
                {cancelLabel}
              </Button>
            ) : null}
            <p className="policy-welcome-note">
              Please review these policies before signing in. Last updated{" "}
              {LEGAL_LAST_UPDATED}.
            </p>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
