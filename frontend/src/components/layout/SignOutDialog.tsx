import { Loader2, LogOut } from "lucide-react"
import { useRef, useState, type RefObject } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useAuth } from "@/features/auth/AuthContext"
import "./sign-out-dialog.css"

export function SignOutDialog({
  open,
  onOpenChange,
  returnFocusRef,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  returnFocusRef: RefObject<HTMLButtonElement | null>
}) {
  const { logout } = useAuth()
  const [pending, setPending] = useState(false)
  const signingOut = useRef(false)
  const cancelRef = useRef<HTMLButtonElement>(null)

  async function confirmSignOut() {
    if (signingOut.current) return
    signingOut.current = true
    setPending(true)
    try {
      await logout()
      onOpenChange(false)
    } finally {
      signingOut.current = false
      setPending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!signingOut.current) onOpenChange(nextOpen)
      }}
    >
      <DialogContent
        role="alertdialog"
        className="sign-out-dialog ring-0"
        showCloseButton={false}
        aria-busy={pending}
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          cancelRef.current?.focus()
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault()
          returnFocusRef.current?.focus({ preventScroll: true })
        }}
      >
        <DialogHeader className="sign-out-heading">
          <div className="sign-out-icon" aria-hidden="true">
            <LogOut />
          </div>
          <DialogTitle>Sign out of AEGIS?</DialogTitle>
          <DialogDescription>
            You’ll return to the sign-in page. You can sign in again anytime.
          </DialogDescription>
        </DialogHeader>
        <div className="sign-out-actions">
          <Button
            ref={cancelRef}
            type="button"
            variant="outline"
            disabled={pending}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={pending}
            onClick={() => void confirmSignOut()}
          >
            {pending ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Signing out…
              </>
            ) : (
              <>
                <LogOut className="size-4" aria-hidden="true" />
                Sign out
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
