import { useRef, useState } from "react"

import { Dialog, DialogContent } from "@/components/ui/dialog"
import { PrivacyPolicyPage } from "./PrivacyPolicyPage"
import { TermsOfUsePage } from "./TermsOfUsePage"
import "./login-legal-policies.css"

export function LoginLegalPolicies() {
  const [policy, setPolicy] = useState<"terms" | "privacy">("terms")
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement | null>(null)

  function openPolicy(
    nextPolicy: "terms" | "privacy",
    button: HTMLButtonElement
  ) {
    trigger.current = button
    setPolicy(nextPolicy)
    setOpen(true)
  }

  return (
    <>
      <p className="login-policy-consent">
        <span className="login-policy-clause">
          By signing in, you agree to the{" "}
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={(event) => openPolicy("terms", event.currentTarget)}
          >
            Terms of Use
          </button>
        </span>{" "}
        <span className="login-policy-clause">
          and acknowledge the{" "}
          <span className="login-policy-link">
            <button
              type="button"
              aria-haspopup="dialog"
              onClick={(event) => openPolicy("privacy", event.currentTarget)}
            >
              Privacy Policy
            </button>
            .
          </span>
        </span>
      </p>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="login-policy-dialog"
          showCloseButton={false}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            trigger.current?.focus({ preventScroll: true })
          }}
        >
          {policy === "terms" ? (
            <TermsOfUsePage presentation="dialog" />
          ) : (
            <PrivacyPolicyPage presentation="dialog" />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
