// Run with: node scripts/check-status-badges.cjs
// Uses actual rendered Badge markup without requiring a browser or test workers.
const assert = require("node:assert/strict")
const path = require("node:path")
const Module = require("node:module")
const { buildSync } = require("esbuild")
const React = require("react")
const { renderToStaticMarkup } = require("react-dom/server")

const root = path.resolve(__dirname, "..")
function bundle(relative) {
  const { outputFiles } = buildSync({
    entryPoints: [path.join(root, relative)],
    bundle: true,
    platform: "node",
    format: "cjs",
    jsx: "automatic",
    packages: "external",
    alias: { "@": path.join(root, "src") },
    write: false,
    logLevel: "silent",
  })
  const compiled = new Module(
    path.join(root, "scripts", "status-check.cjs"),
    module
  )
  compiled.filename = compiled.id
  compiled.filename = compiled.id
  compiled.paths = module.paths
  compiled._compile(outputFiles[0].text, compiled.filename)
  return compiled.exports
}

const { statusTone, statusBadgeClass, riskLevelBadgeClass } = bundle(
  "src/lib/status-badge.ts"
)
const { Badge } = bundle("src/components/ui/badge.tsx")
const groups = {
  success: ["low", "positive", "approved", "completed", "finalized", "present"],
  warning: [
    "moderate",
    "medium",
    "pending",
    "warning",
    "submitted",
    "follow_up",
    "late",
  ],
  danger: [
    "high",
    "severe",
    "critical",
    "incident",
    "rejected",
    "failed",
    "absent",
  ],
  info: ["processing", "excused"],
  neutral: ["draft", "cancelled", "unrecognized", "Academic", "__proto__"],
}
let checks = 0
for (const [tone, statuses] of Object.entries(groups)) {
  for (const status of statuses) {
    assert.equal(statusTone(status), tone, status)
    const html = renderToStaticMarkup(
      React.createElement(Badge, { status, variant: "secondary" }, status)
    )
    assert.ok(html.includes(`data-tone="${tone}"`), status)
    assert.ok(
      html.includes('aria-hidden="true"'),
      "The decorative dot must be hidden from assistive technology"
    )
    assert.ok(
      html.includes(`>${status}</span>`),
      "Keep the readable status label"
    )
    checks++
  }
}
assert.equal(statusTone("  In Progress  "), "warning")
assert.equal(statusTone("below-passing"), "danger")
assert.equal(riskLevelBadgeClass("medium"), statusBadgeClass("moderate"))
const plain = renderToStaticMarkup(
  React.createElement(Badge, null, "Section A")
)
assert.ok(
  !plain.includes("data-tone="),
  "Ordinary category badges must retain their styling"
)
const approved = renderToStaticMarkup(
  React.createElement(
    Badge,
    {
      status: "approved",
      className: "bg-primary text-primary-foreground shrink-0",
    },
    "Approved"
  )
)
assert.ok(approved.includes("bg-emerald-50"))
assert.ok(
  !approved.includes("bg-primary "),
  "Status colors must override old brand fills"
)
assert.ok(approved.includes("shrink-0"), "Preserve layout classes")
console.log(
  `Passed ${checks} status render cases, normalization, fallback and class override checks.`
)
