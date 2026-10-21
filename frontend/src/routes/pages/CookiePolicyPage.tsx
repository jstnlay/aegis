import { LegalPageLayout } from "@/routes/pages/LegalPageLayout"

export function CookiePolicyPage() {
  return (
    <LegalPageLayout
      title="Cookie Policy"
      intro="This page lists everything AEGIS stores in your browser: five items, all of them needed for the portal to work."
    >
      <section aria-labelledby="cookies-none" className="space-y-3">
        <h2 id="cookies-none" className="text-lg font-semibold text-primary">
          AEGIS sets no cookies
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          AEGIS does not use cookies, analytics, advertising or third-party
          tracking scripts. It does use your browser's own storage for the five
          items below. They stay on your device and are not sent to anyone
          outside the school.
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
                  Keeps you signed in between pages.
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
                  Until you sign out, or another account signs in on this
                  browser.
                </td>
              </tr>
              <tr className="border-b border-border/60">
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal text-foreground"
                >
                  aegis:hero-entrance-seen
                </th>
                <td className="py-2 pr-4">Session storage</td>
                <td className="py-2 pr-4">
                  Stops the landing page entrance animation from replaying on
                  every visit.
                </td>
                <td className="py-2">Until you close the tab or browser.</td>
              </tr>
              <tr className="border-b border-border/60">
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal text-foreground"
                >
                  aegis:archive:consultations
                </th>
                <td className="py-2 pr-4">Local storage</td>
                <td className="py-2 pr-4">
                  Remembers your choice to hide completed consultations. Hiding
                  changes the list only; the records stay on the server.
                </td>
                <td className="py-2">Until you clear browser data.</td>
              </tr>
              <tr>
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal text-foreground"
                >
                  aegis:archive:interventions
                </th>
                <td className="py-2 pr-4">Local storage</td>
                <td className="py-2 pr-4">
                  Remembers your choice to hide completed interventions. Hiding
                  changes the list only; the records stay on the server.
                </td>
                <td className="py-2">Until you clear browser data.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          None of these items is used to build a profile or shared with a third
          party.
        </p>
      </section>

      <section aria-labelledby="cookies-banner" className="space-y-3">
        <h2 id="cookies-banner" className="text-lg font-semibold text-primary">
          Why there is no accept button
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Consent banners ask permission for storage that is not needed to run
          the site. All five items above are needed, so there is nothing to ask.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          If the school adds non-essential storage or third-party tooling, this
          page will say so and ask before storing anything.
        </p>
      </section>

      <section aria-labelledby="cookies-manage" className="space-y-3">
        <h2 id="cookies-manage" className="text-lg font-semibold text-primary">
          Removing what is stored
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Clear site data in your browser settings at any time. This signs you
          out; sign in again with your school account.
        </p>
      </section>
    </LegalPageLayout>
  )
}
