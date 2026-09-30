import { Link } from "react-router-dom"
import { SearchX } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"

export function NotFoundPage() {
  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4 py-10">
      <Card className="w-full max-w-md">
        <CardHeader className="gap-2 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
            <SearchX className="size-6" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-foreground">Page not found</h1>
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
    </div>
  )
}
