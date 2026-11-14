# Dashboard (frontend)

React 19 + TypeScript, built with Vite. Code in `frontend/src/`. It talks to the backend
described in [API.md](API.md) and has no other server of its own.

## Run it

    cd frontend
    npm install
    npm run build        # makes frontend/dist, which the API then serves at http://localhost:8000
    npm run dev          # development: http://localhost:5173, /api is forwarded to port 8000
    npm test             # 91 tests (Vitest, Testing Library)
    npm run typecheck

Start the API first: `python -m uvicorn amp_triage.api.main:app --port 8000`. If it is not
running, every page shows a red banner with that command.

## Pages

| Address | What it does |
|---|---|
| `/` | All runs (live and precomputed) with status and progress; delete a run |
| `/new` | Start a run from UniProt accessions, pasted FASTA, or an organism (live search, random sample) |
| `/runs/:id` | Progress while scanning; then the results (below) |
| `/runs/:id/candidate?...` | One candidate: scores, 13 properties, helical wheel, composition, alignment against the closest known AMP, notes |
| `/about` | The pipeline in plain words, the test results (read from the backend), the limits |

### The results page

* **Ranking panel**: sliders for the three exponents of `activity^a x (1 - hemolysis)^s x
  novelty^n`, the assumed rarity of AMPs (log scale), filters (novelty class, hide known,
  hemolysis band, length, protein). Every change re-ranks the saved shortlist on the server;
  nothing is scanned again. The whole view lives in the address, so a link reproduces it.
* **Ranked list** (25 per page, keyboard-reachable links), **Activity vs safety** scatter
  (activity on a log axis, hover finds the nearest dot, click opens it), **Proteins** (a map of
  where the candidates sit along one protein).
* **Export CSV** downloads the current view.

## Design rules it follows

* Colour never carries meaning alone: every colour has a word, hemolysis bands also an icon.
* Charts use the validated categorical palette slots 1 to 3 (blue, orange, aqua) and the fixed
  status colours; dark mode uses the same hues stepped for the dark surface. The ranked list is
  the table view of every chart.
* Charts are drawn at their real width (a scaled-down SVG shrinks its text and marks).
* While data reloads, the previous result stays on screen, dimmed, instead of blanking.
* The honest caveats are on the screen where the numbers are: the activity number is an
  ordering, hemolysis is a band, "novel" does not mean "an AMP".

## Code map

    src/api/        typed client (client.ts) and the shapes of the backend's JSON (types.ts)
    src/lib/        view <-> URL, formatting, helical wheel geometry (all unit-tested)
    src/hooks/      useAsync (keeps old data while loading, drops stale answers), useRunStatus
                    (polling), useDebounced, useElementWidth
    src/components/ the chips, controls, table and charts
    src/pages/      one file per page
    src/test/       fixtures shared by the tests
