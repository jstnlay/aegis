import { LegalPageLayout } from "@/routes/pages/LegalPageLayout"

/**
 * Cookie Policy.
 *
 * The audit found no cookie is ever set: the API authenticates with bearer
 * tokens held in `localStorage`, and the only other browser storage is one
 * `sessionStorage` flag on the landing page. The three keys below are the
 * complete list, and they are named exactly as the code names them
 * (`@/lib/auth-storage`, `@/routes/pages/LandingPage`). If any of those change,
 * this page changes with them.
 *
 * That is also why the site carries no accept/reject banner: there is no
 * non-essential storage to consent to. The one-line notice in the site footer
 * is the whole disclosure.
 */
export function CookiePolicyPage() {
  return (
    <LegalPageLayout
      title="Cookie Policy"
      intro="This page lists everything AEGIS stores in your browser. The list is short, because the portal is deliberately built to hold as little as possible."
    >
      <section aria-labelledby="cookies-none" className="space-y-3">
        <h2 id="cookies-none" className="text-lg font-semibold text-primary">
          AEGIS sets no cookies
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          A cookie is a small file a site asks your browser to send back with
          every request. AEGIS does not use cookies at all. It does not use
          analytics, advertising or tracking of any kind, and it loads no
          third-party script that could set one.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          AEGIS does store three small items in your browser's own storage. They
          stay on your device and are sent only to the school's own server, as
          part of normal requests. They are listed in full below.
        </p>
      </section>

      <section aria-labelledby="cookies-list" className="space-y-3">
        <h2 id="cookies-list" className="text-lg font-semibold text-primary">
          What is stored, and why
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <caption className="sr-only">
              Browser storage used by AEGIS, with its purpose and lifetime
            </caption>
            <thead>
              <tr className="border-b border-border text-left">
                <th scope="col" className="py-2 pr-4 font-medium">
                  Name
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  Where
                </th>
                <th scope="col" className="py-2 pr-4 font-medium">
                  Why
                </th>
                <th scope="col" className="py-2 font-medium">
                  Lifetime
                </th>
              </tr>
            </thead>
            <tbody className="align-top text-muted-foreground">
              <tr className="border-b border-border/60">
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal text-foreground"
                >
                  aegis.access_token
                </th>
                <td className="py-2 pr-4">Local storage</td>
                <td className="py-2 pr-4">
                  Proves who you are on each request, so you stay signed in
                  while you move between pages.
                </td>
                <td className="py-2">
                  Until you sign out or the token expires.
                </td>
              </tr>
              <tr className="border-b border-border/60">
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal text-foreground"
                >
                  aegis.refresh_token
                </th>
                <td className="py-2 pr-4">Local storage</td>
                <td className="py-2 pr-4">
                  Renews your session without asking for your password again.
                </td>
                <td className="py-2">
                  Until you sign out, or until another account signs in on this
                  browser.
                </td>
              </tr>
              <tr>
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal text-foreground"
                >
                  aegis:hero-entrance-seen
                </th>
                <td className="py-2 pr-4">Session storage</td>
                <td className="py-2 pr-4">
                  Remembers that the landing page's entrance animation has
                  already played, so it does not replay on every visit.
                </td>
                <td className="py-2">Until you close the tab or browser.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          None of these items identifies you to anyone outside the school. None
          is used to build a profile, and none is shared.
        </p>
      </section>

      <section aria-labelledby="cookies-banner" className="space-y-3">
        <h2 id="cookies-banner" className="text-lg font-semibold text-primary">
          Why there is no accept button
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Consent banners exist to ask permission for storage that is not needed
          to run the site. Everything listed above is needed for the portal to
          work, and there is nothing else to ask about. So the site tells you
          what it stores — in the footer and on this page — instead of asking
          you to dismiss a banner.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          If the school ever adds a feature that needs non-essential storage or
          third-party tooling, this page will say so and a real choice will be
          offered before anything is stored.
        </p>
      </section>

      <section aria-labelledby="cookies-manage" className="space-y-3">
        <h2 id="cookies-manage" className="text-lg font-semibold text-primary">
          Removing what is stored
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          You can clear this browser storage at any time from your browser's
          settings, under site data or storage. Doing so signs you out; you can
          sign in again with your school account.
        </p>
      </section>
    </LegalPageLayout>
  )
}
