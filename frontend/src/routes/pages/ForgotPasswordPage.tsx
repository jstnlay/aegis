import { useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowRight,
  Clock3,
  KeyRound,
  Loader2,
  MailCheck,
  Mail,
} from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { forgotPasswordRequest } from "@/features/auth/api"
import { normalizeApiError } from "@/lib/error"
import { PasswordRecoveryLayout } from "./PasswordRecoveryLayout"

const forgotSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
})

type ForgotFormValues = z.infer<typeof forgotSchema>

/**
 * Forgot password (document element 4).
 *
 * The page says the same thing whether or not the address belongs to an
 * account, because the server answers the same way. The page cannot be used
 * to find out who has an account, and it must not pretend otherwise by
 * showing a different message for a known address.
 */
export function ForgotPasswordPage() {
  const [serverError, setServerError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const form = useForm<ForgotFormValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  async function onSubmit(values: ForgotFormValues) {
    setServerError(null)
    try {
      await forgotPasswordRequest(values.email)
      setSent(true)
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.isCancelled) return
      setServerError(normalized.message)
    }
  }

  if (sent) {
    return (
      <PasswordRecoveryLayout
        title="Check your inbox"
        description="If an account exists for that address, a password reset link is on its way. The link stops working in 30 minutes and can only be used once."
        icon={MailCheck}
        step={2}
        success
      >
        <div className="school-recovery-note">
          <Mail aria-hidden="true" />
          <p>
            Can’t find the email? Check your spam or junk folder before
            requesting another link.
          </p>
        </div>
        <Button asChild variant="outline" className="w-full">
          <Link to="/login">
            Back to sign in
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      </PasswordRecoveryLayout>
    )
  }

  return (
    <PasswordRecoveryLayout
      title="Reset your password"
      description="Enter the address you sign in with and we will send a link to choose a new password."
      icon={KeyRound}
      step={1}
    >
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
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="email"
                    placeholder="you@school.edu"
                    autoComplete="email"
                    inputMode="email"
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
                Sending...
              </>
            ) : (
              <>
                Send reset link
                <ArrowRight aria-hidden="true" />
              </>
            )}
          </Button>

          <div className="school-recovery-note">
            <Clock3 aria-hidden="true" />
            <p>
              Your reset link is valid for <strong>30 minutes</strong> and can
              be used once.
            </p>
          </div>
        </form>
      </Form>
    </PasswordRecoveryLayout>
  )
}
