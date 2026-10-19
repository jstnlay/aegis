import { Link } from "react-router-dom"
import { SearchX } from "lucide-react"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"

/**
 * Shown for any address that does not match a route, signed in or not.
 *
 * It wears the public chrome rather than appearing bare: a mistyped address can
 * arrive from outside the portal, and a page with no header, no way back and no
 * policy links gives the reader nothing to act on. The card itself is a `main`,
 * which the previous version lacked.
 */
export function NotFoundPage() {
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <SchoolHeader>
        <Button asChild size="sm">
          <Link to="/login">Sign in</Link>
        </Button>
      </SchoolHeader>

      <main className="flex flex-1 items-center justify-center px-4 py-16">
        <Card className="w-full max-w-md">
          <CardHeader className="gap-2 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
              <SearchX className="size-6" aria-hidden="true" />
            </div>
            <h1 className="text-xl font-bold text-foreground">
              Page not found
            </h1>
            <CardDescription>
              The address you tried does not exist in AEGIS.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full">
              <Link to="/">Back to home</Link>
            </Button>
          </CardContent>
        </Card>
      </main>

      <PublicFooter />
    </div>
  )
}
