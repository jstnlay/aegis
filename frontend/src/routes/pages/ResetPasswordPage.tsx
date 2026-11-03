import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import {
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Loader2,
  ShieldCheck,
  Link2Off,
} from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { resetPasswordRequest } from "@/features/auth/api"
import { normalizeApiError } from "@/lib/error"
import { PasswordRecoveryLayout } from "./PasswordRecoveryLayout"
import { RecoveryPasswordInput } from "./RecoveryPasswordInput"

const resetSchema = z
  .object({
    new_password: z
      .string()
      .min(1, "New password is required.")
      .min(8, "Password must be at least 8 characters."),
    confirm_password: z.string().min(1, "Please confirm your new password."),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  })

type ResetFormValues = z.infer<typeof resetSchema>

/**
 * Redeem a password link.
 *
 * The token in the query string is the credential: the server decides which
 * account it belongs to, so this page cannot name a different one. A missing
 * or spent token is refused by the server, and the message here says so
 * without guessing why.
 *
 * Two callers, one primitive. A forgotten password and a newly provisioned
 * account both redeem a token on the account; only the wording differs, and
 * only the link that brought the reader here differs.
 */
export function ResetPasswordPage() {
  return <PasswordLinkForm purpose="reset" />
}

/** The same redemption, for the link a newly provisioned account follows. */
export function SetPasswordPage() {
  return <PasswordLinkForm purpose="setup" />
}

function PasswordLinkForm({ purpose }: { purpose: "reset" | "setup" }) {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const [serverError, setServerError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const form = useForm<ResetFormValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { new_password: "", confirm_password: "" },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  async function onSubmit(values: ResetFormValues) {
    setServerError(null)
    try {
      await resetPasswordRequest({
        token,
        new_password: values.new_password,
        confirm_password: values.confirm_password,
      })
      setDone(true)
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.isCancelled) return
      setServerError(normalized.message)
    }
  }

  if (done) {
    return (
      <PasswordRecoveryLayout
        title={purpose === "setup" ? "Password set" : "Password reset"}
        description="Your password has been changed and every signed-in session has been ended. You can sign in now."
        icon={CheckCircle2}
        step={3}
        setup={purpose === "setup"}
        success
      >
        <Button asChild className="w-full">
          <Link to="/login">
            Sign in
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      </PasswordRecoveryLayout>
    )
  }

  return (
    <PasswordRecoveryLayout
      title={
        purpose === "setup" ? "Set your password" : "Choose a new password"
      }
      description={
        token
          ? purpose === "setup"
            ? "Choose the password you will use to sign in. Nobody else knows it."
            : "Pick a new password for your account. Signing in on other devices will require it."
          : purpose === "setup"
            ? "This link is missing its token. Ask the office to send a new one."
            : "This reset link is missing its token. Request a new link and try again."
      }
      icon={token ? KeyRound : Link2Off}
      step={3}
      setup={purpose === "setup"}
      showSteps={Boolean(token)}
    >
      {token ? (
        <Form {...form}>
          <form
            onSubmit={(e) => void form.handleSubmit(onSubmit)(e)}
            className="school-recovery-form"
            noValidate
            aria-busy={isSubmitting}
          >
            {serverError ? (
              <div
                role="alert"
                className="rounded-sm border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive"
              >
                {serverError}
              </div>
            ) : null}

            <FormField
              control={form.control}
              name="new_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>New password</FormLabel>
                  <FormControl>
                    <RecoveryPasswordInput
                      {...field}
                      visibilityLabel="new password"
                      placeholder="Create a new password"
                      disabled={isSubmitting}
                    />
                  </FormControl>
                  <FormDescription className="school-recovery-password-hint">
                    Use at least 8 characters.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="confirm_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Confirm new password</FormLabel>
                  <FormControl>
                    <RecoveryPasswordInput
                      {...field}
                      visibilityLabel="password confirmation"
                      placeholder="Re-enter your new password"
                      disabled={isSubmitting}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Saving...
                </>
              ) : (
                <>
                  Set new password
                  <ArrowRight aria-hidden="true" />
                </>
              )}
            </Button>
            <div className="school-recovery-note">
              <ShieldCheck aria-hidden="true" />
              <p>
                After resetting, sign in again on your other devices with your
                new password.
              </p>
            </div>
          </form>
        </Form>
      ) : (
        <Button asChild className="w-full">
          <Link to="/forgot-password">Request a new link</Link>
        </Button>
      )}
    </PasswordRecoveryLayout>
  )
}
