# FIX Checker

Windows desktop application that tests a website after local Git commits, using
Skyvern AI or browser-use. The existing Home, Run Agent, Regression Tasks and
Settings pages are preserved.

## Install without an IDE (Windows, Python 3.12+)

1. Install standard Python 3.12 or newer if it is not already installed. Include
   the Python launcher, Tcl/Tk and pip in the Python installer. Git must also be
   installed to monitor local repositories.
2. Download/extract the project, then double-click **`setup.bat`**. An internet
   connection is required. Setup creates both environments, installs all Python
   packages and downloads Chromium for each browser engine. Leave the window open
   until it says setup completed; errors remain visible if installation fails.
3. Double-click **`start.bat`** to open FIX Checker. No IDE or terminal commands
   are required. You can run setup again to repair or finish an installation.

For command-line installation, run from PowerShell in this directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
.\start.ps1
```

Setup detects the Python launcher, existing project environments and Python on
PATH. If needed, supply an installed interpreter explicitly:

```powershell
.\setup.bat -Python 'C:\path\to\python.exe'
```

The main dependencies are customtkinter, browser-use, langchain-openai,
playwright, GitPython and pydantic. Skyvern installs as `skyvern[local]` in
`.skyvern-venv`. Its dependencies conflict with those of browser-use, so do not
install both in the same environment. `setup.ps1` keeps them separate.

## Configure and run

1. Open Settings. Enter your own OpenAI API key (or set `OPENAI_API_KEY` before
   starting the app), model `gpt-6-luna`, and the base URL of your running site.
2. Select a local Git repository and the browser engine. Skyvern is the default;
   browser-use is also available. Save settings.
3. In Regression Tasks, add or edit each flow's name, starting path and precise
   steps, including prerequisites, test credentials if needed and expected results.
4. In Run Agent, enter a starting path or a full HTTP(S) URL, describe the fix
   trajectory, and select the current fix and/or saved regressions.
5. Enable Show browser live to watch Chromium. Launch the agent or use Test latest
   commit. Cancel stops the active run and closes its browser.

The monitor polls local HEAD every three seconds; it does not poll GitHub's API.
New commits queue while a test is running. The selected repo can be changed or
cleared in Settings. Checking a commit does not build, deploy or switch the site
itself: the website URL must already serve the version you intend to verify.

## Engines and reports

Both engines operate on an isolated local Chromium profile, including for
localhost sites. Skyvern uses its embedded API and an ephemeral SQLite database;
it does not require Skyvern Cloud, a Skyvern API key, Docker or PostgreSQL.
The OpenAI model and API key come from Settings. Skyvern runs in a separate
process and streams logs to the application's background asyncio worker.
browser-use uses its native ChatOpenAI adapter; newer releases no longer accept
a LangChain model as the agent's LLM.

The desktop event pump receives worker messages through queues. Browsing and AI
calls run outside the Tk thread. A run is limited to 100 agent steps and 15
minutes. The first observed JavaScript/console error, HTTP 404 or HTTP 5xx stops
the run and produces FAILED with the URL, current agent step and error.
Otherwise, only a validated structured agent result can produce PASSED:

```json
{
  "status": "FAILED",
  "stopped_at_step": 3,
  "stopped_url": "http://localhost:3000/settings",
  "failed_test_name": "Save settings",
  "error_details": "Save button is missing."
}
```

Steps reported by browser diagnostics are engine action steps; one action may
include several UI operations. Infrastructure failures use step 0. Network
failure reports use the failing resource URL. Without test credentials the agent
must report failure rather than inventing an account. AI-driven checks still
require review of the recorded evidence and clear expected outcomes.

Home supports search, status/source filters and viewing historical reports.
New manual runs never overwrite earlier results. Incoming commits cannot take
ownership of an already-running test's result.

Settings, selected tasks and up to 50 history entries live in `settings.json`,
`tasks.json` and `history.json` in the project directory, independently of the
working directory. The key field is masked; a key saved through Settings is
stored as plaintext in settings.json. Local state, credentials, environments and
agent artifacts are excluded by .gitignore. No API key ships with the project.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.smoke_desktop
.\.skyvern-venv\Scripts\python.exe -m tests.smoke_skyvern
```

Unit tests cover strict report validation, URLs, selected flows, persistence,
Git monitor restarts, concurrency, cancellation, first-error stopping and run
ownership. Desktop smoke checks open every page and the task editor, run a local
fixture in real Chromium, attach browser-use and verify console/HTTP diagnostics.
The browser-use agent smoke uses simulated LLM responses and real browser actions.
The Skyvern smoke initializes its actual embedded API and in-memory database.
These checks make no paid model calls. A full AI test requires your API key and
running target website.

API references used for the integrations:
[Skyvern SDK](https://github.com/Skyvern-AI/skyvern/blob/main/docs/sdk-reference/complete-reference.mdx),
[browser-use agent parameters](https://docs.browser-use.com/open-source/customize/agent/all-parameters),
[OpenAI GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna).
