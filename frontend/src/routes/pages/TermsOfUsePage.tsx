import { LegalPageLayout } from "@/routes/pages/LegalPageLayout"

export function TermsOfUsePage() {
  return (
    <LegalPageLayout
      title="Terms of Use"
      intro="These terms cover your use of AEGIS, the school's information system: what the school expects from you, and what you can expect from the system."
    >
      <section aria-labelledby="terms-accept" className="space-y-3">
        <h2 id="terms-accept" className="text-lg font-semibold text-primary">
          Accepting these terms
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          By signing in to AEGIS you accept these terms. If you do not accept
          them, do not use the portal and tell the school office, so your
          child's information can be recorded on paper instead.
        </p>
      </section>

      <section aria-labelledby="terms-account" className="space-y-3">
        <h2 id="terms-account" className="text-lg font-semibold text-primary">
          Your account
        </h2>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
          <li>
            Accounts are issued by the school. You may not create one for
            yourself or for anyone else.
          </li>
          <li>
            Keep your password to yourself. Do not let anyone else sign in with
            your account.
          </li>
          <li>
            If you think someone else knows your password, change it in Account
            Settings and tell the registrar.
          </li>
          <li>
            Signing in on a shared computer signs the other account out. Sign
            out when you finish.
          </li>
        </ul>
      </section>

      <section aria-labelledby="terms-use" className="space-y-3">
        <h2 id="terms-use" className="text-lg font-semibold text-primary">
          What you may and may not do
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Use AEGIS for school purposes: your own studies, your own classes, or
          your own children's records. You must not:
        </p>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
          <li>
            try to reach records that belong to another family or another class;
          </li>
          <li>
            copy, scrape or bulk-export information beyond the downloads the
            portal offers you;
          </li>
          <li>
            share records, screenshots or downloaded files with anyone not
            entitled to them;
          </li>
          <li>
            attempt to break, overload, probe or bypass the system's access
            checks; or
          </li>
          <li>upload files that contain anything unlawful or harmful.</li>
        </ul>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The server decides what each account can reach. Trying to reach more
          than your role allows breaches these terms even if the attempt fails.
        </p>
      </section>

      <section aria-labelledby="terms-records" className="space-y-3">
        <h2 id="terms-records" className="text-lg font-semibold text-primary">
          School records
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Grades, attendance and guidance records shown in AEGIS are official
          school records. Students and parents cannot edit them from the portal.
          If something is wrong, ask the registrar or the teacher concerned.
          Correction is a school decision, made on evidence, not a self-service
          button.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Guidance records are confidential to the guidance office. They are
          visible to a parent or guardian where the school judges that it helps
          the student's welfare.
        </p>
      </section>

      <section aria-labelledby="terms-fees" className="space-y-3">
        <h2 id="terms-fees" className="text-lg font-semibold text-primary">
          No fees
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          AEGIS is provided by the school to its students, parents and staff at
          no charge. The portal takes no payment and processes no payment
          details. Tuition and other school fees are handled through the school
          office.
        </p>
      </section>

      <section aria-labelledby="terms-availability" className="space-y-3">
        <h2
          id="terms-availability"
          className="text-lg font-semibold text-primary"
        >
          Availability
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The school maintains AEGIS for use during the school day, but it may
          be unavailable for maintenance, updates or faults. When a part of the
          system cannot load, the portal says so rather than showing an empty
          page.
        </p>
      </section>

      <section aria-labelledby="terms-ip" className="space-y-3">
        <h2 id="terms-ip" className="text-lg font-semibold text-primary">
          Ownership
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The school's name, seal and campus images belong to the school. The
          AEGIS software and its design belong to their respective owners. You
          may not reuse either outside your school business without permission.
        </p>
      </section>

      <section aria-labelledby="terms-suspension" className="space-y-3">
        <h2
          id="terms-suspension"
          className="text-lg font-semibold text-primary"
        >
          Ending access
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The school may suspend or close an account that breaches these terms,
          or when a person leaves the school. Academic records stay with the
          school in line with the Privacy Policy.
        </p>
      </section>

      <section aria-labelledby="terms-liability" className="space-y-3">
        <h2 id="terms-liability" className="text-lg font-semibold text-primary">
          Limits
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The school takes reasonable care to keep AEGIS accurate and available.
          It is not liable for losses caused by a person misusing the system or
          by circumstances beyond its control. Nothing here removes a right you
          have under the Data Privacy Act of 2012 or any other law.
        </p>
      </section>

      <section aria-labelledby="terms-law" className="space-y-3">
        <h2 id="terms-law" className="text-lg font-semibold text-primary">
          Governing law and changes
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          These terms are governed by the laws of the Republic of the
          Philippines. When they change, the date at the top of the page changes
          with them.
        </p>
      </section>
    </LegalPageLayout>
  )
}
