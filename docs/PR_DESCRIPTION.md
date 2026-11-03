Title: Refresh school portals, responsive layouts, and semantic status colors

## Summary

Improve the AEGIS frontend with clearer academic workflows, consistent school branding, and responsive layouts for desktop and mobile.

## Changes

- Refine the public homepage, school branding, navigation, backgrounds, and mobile layouts.
- Update login, registration, password recovery, and legal pages with coordinated layouts and artwork.
- Improve the shared sidebar, header, account actions, sign-out dialog, tabs, and table presentation.
- Refresh the administrator, guidance, student, parent, and faculty workspaces.
- Add illustrated faculty classroom cards, subject colors, a welcome banner, and organized teaching actions.
- Improve the parent student picker and share the selected student across parent pages within the current session; reset grading-period selection when switching students.
- Remove the floating chatbot from the parent workspace.
- Apply consistent status badges: green for positive/success states, amber for warnings and pending work, red for high severity and failures, blue for informational states, and gray for neutral states.
- Separate the guidance roster query cache from the student activity directory.
- Add frontend API proxy URL handling, Vercel API rewrites, and environment configuration examples.
- Update related regression tests and add a focused status badge render check.

## Validation

- Production frontend build passed.
- TypeScript project check passed.
- Faculty dashboard tests passed: 2 tests.
- Focused status badge checks passed: 27 render cases plus normalization, fallback, and class override checks.
- The full regression suite and visual browser checks across desktop and mobile have not been completed.

## Review focus

- Review the responsive layouts and navigation across all five roles.
- Check parent student switching, account screens, and semantic status colors.
- Verify API proxy behavior against the deployment environment.
