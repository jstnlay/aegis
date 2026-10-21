import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { CheckCircle2, Loader2, MailCheck } from "lucide-react"
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
import { acceptParentInvitationRequest } from "@/features/auth/api"
import { normalizeApiError } from "@/lib/error"

const acceptSchema = z
  .object({
    password: z
      .string()
      .min(1, "Password is required.")
      .min(8, "Password must be at least 8 characters."),
    confirm_password: z.string().min(1, "Please confirm your password."),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match.",
    path: ["confirm_password"],
  })

type AcceptFormValues = z.infer<typeof acceptSchema>

/**
 * Accept a parent invitation.
 *
 * The school issued this link, so the account and the child it opens are
 * both decided by the invitation. The parent only chooses a password.
 */
export function AcceptInvitationPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const [serverError, setServerError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const form = useForm<AcceptFormValues>({
    resolver: zodResolver(acceptSchema),
    defaultValues: { password: "", confirm_password: "" },
    mode: "onBlur",
  })

  const isSubmitting = form.formState.isSubmitting

  async function onSubmit(values: AcceptFormValues) {
    setServerError(null)
    try {
      await acceptParentInvitationRequest({
        token,
        password: values.password,
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
              Your parent account is ready
            </h1>
            <CardDescription>
              Sign in with the email address the invitation was sent to and the
              password you just chose.
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
            <MailCheck className="size-6" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-foreground">
            Choose a password
          </h1>
          <CardDescription>
            {token
              ? "The school invited you to follow your child's academic record. Set a password to finish."
              : "This invitation link is missing its token. Ask the school to send a new one."}
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
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Password</FormLabel>
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
                      <FormLabel>Confirm password</FormLabel>
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
                    "Create my account"
                  )}
                </Button>
              </form>
            </Form>
          ) : (
            <Button asChild className="w-full">
              <Link to="/login">Back to sign in</Link>
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
