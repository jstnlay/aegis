# Phone layouts (390 x 844)

Reference captures of the AEGIS app at phone width, taken from the running
build at `http://127.0.0.1:5173` with a 390x844 mobile viewport.

| File | Screen | Role |
| --- | --- | --- |
| `landing.png` | Public landing page | anyone |
| `student-dashboard.png` | Student dashboard | student |
| `parent-dashboard.png` | Parent dashboard | parent |
| `faculty-dashboard.png` | Faculty dashboard | faculty |
| `guidance-dashboard.png` | Guidance dashboard | guidance |
| `admin-dashboard.png` | Administration panel | admin |

## Why these exist

The Figma file has no phone frames. The mobile design in the `CAPSTONE-UI` file
is the old prototype, inside the node named `NOT INCLUDE`
(`446:268`, 13169x17158 at -9359,-5514 on the `User` page), so it is not a
reference. The phone layouts above were designed from the current desktop
frames instead:

- Guidance: `695:281` "Guidance dashboard" (1920x1080, page `User`)
- Admin: `259:278` "Dashboard" (1440x1024, page `Admin`)
- Faculty: `577:34` "Dashboard" (1440x1024, page `Admin`)
- Landing: `652:48`, `653:69`, `657:2` (1920x1080, page `User`)

## Rules the phone layouts follow

- The sidebar collapses into a drawer; the top bar keeps the page name, the
  notification bell and the account menu.
- Metric rows are two tiles wide. A single headline figure spans the full
  width, with the supporting figures beside it.
- Data tables keep their columns and scroll sideways inside their own
  container, instead of squeezing every column into a few characters.
- Names, codes, dates and emails never wrap mid-value.
- The landing hero drops the campus photo below `md`; the headline sat on the
  gate signage at phone width and neither was readable.

## Regenerating

```
npm run dev                 # frontend on 127.0.0.1:5173
# then sign in as the role and capture a 390x844 full-page screenshot
```

## Pushing these into Figma

`figma/` holds the phone screens as Design Bridge specs, ready to render onto
the canvas as editable frames:

| File | Screen |
| --- | --- |
| `aegis-landing-mobile.json` | Public landing page |
| `aegis-student-dashboard-mobile.json` | Student dashboard |
| `aegis-parent-dashboard-mobile.json` | Parent dashboard |
| `aegis-faculty-dashboard-mobile.json` | Faculty dashboard |
| `aegis-guidance-dashboard-mobile.json` | Guidance dashboard |
| `aegis-admin-dashboard-mobile.json` | Administration panel |

They are generated, not hand-edited:

```
node docs/mobile/figma/generate-specs.cjs
```

Each spec is validated against the bridge schema
(`C:/Users/Lay/Tools/figma-design-bridge/src/schema.js`) before it is sent.

To render them, the Figma desktop app must be open on `CAPSTONE-UI` with the
`Design Bridge` plugin running (green dot), and the `figma-bridge` MCP server
must be up. The plugin connects to the bridge on port 3055; if another
instance of `figma-design-bridge/src/server.js` is already running, stop it
first, or start the bridge with `--port <n>` and set the same port in the
plugin.

The PNGs above can also be dropped onto the canvas as flat references.
