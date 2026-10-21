import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { CheckCircle2, KeyRound, Loader2 } from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { resetPasswordRequest } from "@/features/auth/api"
import { normalizeApiError } from "@/lib/error"

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
      <div
        role="status"
        className="flex min-h-svh items-center justify-center bg-background px-4 py-10"
      >
        <Card className="w-full max-w-md">
          <CardHeader className="gap-2 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-success text-success-foreground">
              <CheckCircle2 className="size-6" aria-hidden="true" />
            </div>
            <h1 className="text-xl font-bold text-foreground">
              {purpose === "setup" ? "Password set" : "Password reset"}
            </h1>
            <CardDescription>
              Your password has been changed and every signed-in session has
              been ended. You can sign in now.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link to="/login">Sign in</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4 py-10">
      <Card className="w-full max-w-md">
        <CardHeader className="gap-2 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <KeyRound className="size-6" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-foreground">
            {purpose === "setup"
              ? "Set your password"
              : "Choose a new password"}
          </h1>
          <CardDescription>
            {token
              ? purpose === "setup"
                ? "Choose the password you will use to sign in. Nobody else knows it."
                : "Pick a new password for your account. Signing in on other devices will require it."
              : purpose === "setup"
                ? "This link is missing its token. Ask the office to send a new one."
                : "This reset link is missing its token. Request a new link and try again."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {token ? (
            <Form {...form}>
              <form
                onSubmit={(e) => void form.handleSubmit(onSubmit)(e)}
                className="space-y-4"
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
                        <Input
                          {...field}
                          type="password"
                          autoComplete="new-password"
                          disabled={isSubmitting}
                        />
                      </FormControl>
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
                        <Input
                          {...field}
                          type="password"
                          autoComplete="new-password"
                          disabled={isSubmitting}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2
                        className="size-4 animate-spin"
                        aria-hidden="true"
                      />
                      Saving...
                    </>
                  ) : (
                    "Set new password"
                  )}
                </Button>
              </form>
            </Form>
          ) : (
            <Button asChild className="w-full">
              <Link to="/forgot-password">Request a new link</Link>
            </Button>
          )}

          <p className="mt-4 text-center text-sm">
            <Link
              to="/login"
              className="underline underline-offset-4 transition-colors hover:text-foreground"
            >
              Back to sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
