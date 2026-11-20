/**
 * Installability check for the built bundle.
 *
 * A broken manifest, a missing icon or a worker that lost its push handler is
 * invisible until a phone refuses to install the app, so CI fails on it here
 * instead. Run after `npm run build`; it reads `dist/` and nothing else.
 */
import { readFileSync, existsSync } from "node:fs"
import { join } from "node:path"

const dist = join(process.cwd(), "dist")
const failures = []

function fail(message) {
  failures.push(message)
}

const manifestPath = join(dist, "manifest.webmanifest")
if (!existsSync(manifestPath)) {
  fail("dist/manifest.webmanifest is missing")
} else {
  let manifest
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"))
  } catch (error) {
    fail(`dist/manifest.webmanifest is not valid JSON: ${error.message}`)
  }
  if (manifest) {
    for (const field of ["name", "short_name", "start_url", "display", "icons"]) {
      if (!manifest[field]) fail(`manifest is missing "${field}"`)
    }
    if (manifest.start_url && !manifest.start_url.startsWith("/")) {
      fail(`manifest start_url "${manifest.start_url}" is not same-origin`)
    }
    for (const icon of manifest.icons ?? []) {
      const iconPath = join(dist, icon.src.replace(/^\//, ""))
      if (!existsSync(iconPath)) fail(`manifest icon ${icon.src} is not in dist`)
    }
    if (!(manifest.icons ?? []).some((icon) => icon.purpose === "maskable")) {
      fail("manifest has no maskable icon")
    }
  }
}

const swPath = join(dist, "sw.js")
if (!existsSync(swPath)) {
  fail("dist/sw.js is missing")
} else {
  const sw = readFileSync(swPath, "utf8")
  if (!sw.includes("importScripts(\"/push-sw.js\")")) {
    fail("dist/sw.js does not import /push-sw.js, so push would be dead")
  }
}

if (!existsSync(join(dist, "push-sw.js"))) {
  fail("dist/push-sw.js is missing")
}

// The offline page is a build entry of its own; without it the worker's
// navigation fallback would answer an offline request with the app shell.
if (!existsSync(join(dist, "index.html"))) {
  fail("dist/index.html is missing")
}

if (failures.length > 0) {
  console.error("PWA check failed:")
  for (const failure of failures) console.error(`  - ${failure}`)
  process.exit(1)
}

console.log("PWA check passed: manifest, icons, worker and push handler present.")
