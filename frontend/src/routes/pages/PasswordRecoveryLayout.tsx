import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import {
  ArrowLeft,
  Check,
  KeyRound,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react"

import { HomepageBackground } from "@/components/brand/HomepageBackground"
import { SCHOOL_NAME } from "@/lib/school-content"
import "./password-recovery.css"

export function PasswordRecoveryLayout({
  title,
  description,
  icon: Icon,
  step,
  setup = false,
  success = false,
  showSteps = true,
  children,
}: {
  title: string
  description: ReactNode
  icon: LucideIcon
  step: 1 | 2 | 3
  setup?: boolean
  success?: boolean
  showSteps?: boolean
  children: ReactNode
}) {
  const allComplete = success && step === 3
  return (
    <div className="school-recovery-page school-brand-background">
      <HomepageBackground />
      <div className="school-recovery-wrap">
        <Link to="/login" className="school-recovery-back">
          <ArrowLeft aria-hidden="true" />
          Back to sign in
        </Link>
        <div className="school-recovery-shell">
          <aside
            className="school-recovery-story"
            aria-label={setup ? "Account setup" : "Account recovery"}
          >
            <div className="school-recovery-brand">
              <img
                src="/hcci-logo.png"
                alt={SCHOOL_NAME}
                width="44"
                height="44"
              />
              <div>
                <strong>AEGIS</strong>
                <span>{setup ? "Account setup" : "Account recovery"}</span>
              </div>
            </div>
            <div className="school-recovery-art" aria-hidden="true">
              <span />
              <ShieldCheck strokeWidth={1.3} />
              <KeyRound strokeWidth={1.6} />
            </div>
            <div className="school-recovery-story-copy">
              <p className="school-recovery-eyebrow">
                Your school. Your learning space.
              </p>
              <p className="school-recovery-story-title">
                {setup
                  ? "A fresh start for your school account."
                  : "Let’s get you back to learning."}
              </p>
              <p>
                {setup
                  ? "Create your own password to get started with AEGIS."
                  : "A few simple steps, and you’ll be ready to sign in again."}
              </p>
            </div>
            {!setup && showSteps ? (
              <ol
                className="school-recovery-steps"
                aria-label="Password recovery steps"
              >
                {[
                  "Enter your email",
                  "Check your inbox",
                  "Create a new password",
                ].map((label, index) => (
                  <li
                    key={label}
                    data-current={step === index + 1}
                    data-complete={step > index + 1 || allComplete}
                    aria-current={
                      !allComplete && step === index + 1 ? "step" : undefined
                    }
                  >
                    <span aria-hidden="true">
                      {step > index + 1 || allComplete ? <Check /> : index + 1}
                    </span>
                    <span>{label}</span>
                  </li>
                ))}
              </ol>
            ) : null}
          </aside>
          <main
            className="school-recovery-main"
            aria-labelledby="recovery-title"
          >
            <header
              className="school-recovery-heading"
              role={success ? "status" : undefined}
            >
              <span className="school-recovery-icon" data-success={success}>
                <Icon aria-hidden="true" />
              </span>
              <p className="school-recovery-eyebrow">
                {setup ? "Welcome to AEGIS" : "Password assistance"}
              </p>
              <h1 id="recovery-title">{title}</h1>
              <p className="school-recovery-description">{description}</p>
            </header>
            <div className="school-recovery-content">{children}</div>
            <p className="school-recovery-footer">
              Academic Governance and Intervention System
            </p>
          </main>
        </div>
      </div>
    </div>
  )
}
