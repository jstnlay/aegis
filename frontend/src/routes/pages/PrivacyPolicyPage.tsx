import { LegalPageLayout } from "@/routes/pages/LegalPageLayout"

export function PrivacyPolicyPage() {
  return (
    <LegalPageLayout
      title="Privacy Policy"
      intro="What AEGIS holds about you and your child, why it holds it, who can see it, and what you can ask the school to do with it."
    >
      <section aria-labelledby="privacy-who" className="space-y-3">
        <h2 id="privacy-who" className="text-lg font-semibold text-primary">
          Who is responsible
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          His Care Christian Institute is the personal information controller
          for AEGIS. The school decides what the system collects and why. AEGIS
          is software the school runs, not a separate service with its own
          interests in your data.
        </p>
      </section>

      <section aria-labelledby="privacy-collect" className="space-y-3">
        <h2 id="privacy-collect" className="text-lg font-semibold text-primary">
          What AEGIS holds
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Only what the school needs to run the portal. Nothing is collected for
          advertising, and no information is sold.
        </p>
        <dl className="space-y-3 text-sm">
          <div className="space-y-1">
            <dt className="font-medium text-foreground">Your account</dt>
            <dd className="leading-relaxed text-muted-foreground">
              Name, email address, username, role, and account status. Passwords
              are stored only in a form that cannot be read back.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-foreground">
              Contact details you add
            </dt>
            <dd className="leading-relaxed text-muted-foreground">
              Phone number, address, and language preference. These are optional
              and you can change or clear them in Account Settings.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-foreground">Academic records</dt>
            <dd className="leading-relaxed text-muted-foreground">
              Grades, attendance, section and class schedule, and assessment
              submissions. These are school records, held for the same reason a
              paper record is held.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-foreground">Guidance records</dt>
            <dd className="leading-relaxed text-muted-foreground">
              Counselling sessions, intervention plans, behavioural notes and
              wellness assessments. These may include sensitive personal
              information, held so the guidance office can support the student.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-foreground">Family links</dt>
            <dd className="leading-relaxed text-muted-foreground">
              Which students a parent or guardian account is linked to. This is
              what limits a parent to their own children's records.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-foreground">Notifications</dt>
            <dd className="leading-relaxed text-muted-foreground">
              Messages sent to you inside AEGIS, and your delivery preferences
              including quiet hours. You can change these or turn notifications
              off in Account Settings.
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="font-medium text-foreground">
              Administrative trail
            </dt>
            <dd className="leading-relaxed text-muted-foreground">
              A record of actions taken by administrators. It exists so changes
              can be accounted for, and it cannot be edited from the portal.
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="privacy-see" className="space-y-3">
        <h2 id="privacy-see" className="text-lg font-semibold text-primary">
          Who can see it
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Access follows a person's role in the school. The server enforces it
          on every request, not just in the screen you see.
        </p>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
          <li>Students see their own records.</li>
          <li>
            Parents and guardians see the records of the children their account
            is linked to, and no one else's.
          </li>
          <li>
            Teachers see the classes and subjects they handle, and the students
            enrolled in them.
          </li>
          <li>
            The guidance office sees welfare records for the students it
            supports.
          </li>
          <li>
            Administrators see school-wide figures. Where the school has not
            recorded consent for a student, figures are shown in aggregate
            rather than as that student's identifiable grades.
          </li>
        </ul>
      </section>

      <section aria-labelledby="privacy-children" className="space-y-3">
        <h2
          id="privacy-children"
          className="text-lg font-semibold text-primary"
        >
          Children's information
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Most students here are below the age of majority, so a parent or
          guardian gives consent on the student's behalf. The school records
          that consent during enrolment and registration.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Until a student reaches the age of majority, a parent or guardian
          exercises the rights below for them. A student old enough to
          understand can ask about their own information at any time through the
          guidance office or the registrar.
        </p>
      </section>

      <section aria-labelledby="privacy-retention" className="space-y-3">
        <h2
          id="privacy-retention"
          className="text-lg font-semibold text-primary"
        >
          How long it is kept
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Academic records are kept while the student is enrolled, and
          afterwards for as long as the school's records retention schedule
          requires them to be available. Guidance records and the administrative
          trail are kept while needed for the purpose they were collected for.
          The retention schedule sets the exact periods.
        </p>
      </section>

      <section aria-labelledby="privacy-rights" className="space-y-3">
        <h2 id="privacy-rights" className="text-lg font-semibold text-primary">
          Your rights
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Under the Data Privacy Act of 2012 you have the right to:
        </p>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
          <li>be told whether your information is being processed, and why;</li>
          <li>access your information and receive a copy of it;</li>
          <li>
            dispute information that is wrong and have it corrected, completed
            or updated;
          </li>
          <li>
            ask for information to be erased or blocked, where the law allows
            it;
          </li>
          <li>
            object to processing, and withdraw consent where consent applies;
          </li>
          <li>receive your information in a portable form;</li>
          <li>be told about a data breach affecting you;</li>
          <li>lodge a complaint with the National Privacy Commission; and</li>
          <li>claim compensation for damage caused by unlawful processing.</li>
        </ul>
        <p className="text-sm leading-relaxed text-muted-foreground">
          To exercise any of these, write to the school's Data Protection
          Officer using the details at the end of this page. The school will
          confirm what was done.
        </p>
      </section>

      <section aria-labelledby="privacy-security" className="space-y-3">
        <h2
          id="privacy-security"
          className="text-lg font-semibold text-primary"
        >
          Security and breaches
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          AEGIS requires a school-issued account, and the server checks what
          each account may reach on every request. Passwords are never stored in
          readable form and are never sent back to the browser.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          If a breach puts your information at risk, the school will notify the
          National Privacy Commission and the people affected within 72 hours,
          as the law requires.
        </p>
      </section>

      <section aria-labelledby="privacy-sharing" className="space-y-3">
        <h2 id="privacy-sharing" className="text-lg font-semibold text-primary">
          Sharing and third parties
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          AEGIS contains no analytics, advertising or third-party tracking.
          Information is not sold or traded. Records are shared outside the
          school only where the law requires it, or with your consent.
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Public announcements and resources are read from a content service;
          those pages carry no student information.
        </p>
      </section>

      <section aria-labelledby="privacy-changes" className="space-y-3">
        <h2 id="privacy-changes" className="text-lg font-semibold text-primary">
          Changes to this policy
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          When this policy changes, the date at the top of the page changes with
          it. Material changes are announced through the portal.
        </p>
      </section>
    </LegalPageLayout>
  )
}
