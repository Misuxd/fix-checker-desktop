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

1. Open Settings and choose a browser engine. Skyvern is the default: enter your
   **Skyvern API key** (or set `SKYVERN_API_KEY` before starting the app). For
   browser-use, enter your **OpenAI API key** (or set `OPENAI_API_KEY`) and model
   `gpt-6-luna`. Each engine's key is stored separately; changing engines updates
   the sidebar AI name immediately and preserves both keys. The selected engine
   applies immediately; save changes to key, model and other fields separately.
2. Enter the base URL of your running site and select a local Git repository.
   Skyvern Cloud needs a publicly reachable site URL. Use browser-use for
   localhost sites. Save settings.
3. In Regression Tasks, add or edit each flow's name and precise steps, including
   navigation, prerequisites, test credentials if needed and expected results.
4. In Run Agent, select the regression tasks to run. Runs start at the exact Base site URL from Settings;
   describe any further navigation in the test steps.
5. Enable Show browser live before launching to watch the run. With browser-use,
   this opens a local Chromium window; with Skyvern, it opens the cloud session's
   live viewer in your default browser (sign in to Skyvern if prompted). With the
   switch off, runs still produce step logs without opening a browser window or
   viewer. The switch is locked during a run. Launch the agent or use Test latest
   commit. Cancel also requests cancellation of an active Skyvern Cloud run.

The monitor polls local HEAD every three seconds; it does not poll GitHub's API.
New commits queue while a test is running. Use the up/down arrows on a queued
Home card to change the order of waiting commit runs. The selected repo can be changed or
cleared in Settings. Checking a commit does not build, deploy or switch the site
itself: the website URL must already serve the version you intend to verify.

## Engines and reports

Skyvern uses its cloud API, authenticating with the Skyvern API key from Settings.
Skyvern manages the browser and model; the OpenAI model setting applies only to
browser-use. Skyvern runs in a separate process and streams status logs to the
application's background asyncio worker. Cloud browsers cannot reach your
machine's localhost; provide a public deployment or a URL exposed through a
tunnel. When live viewing is enabled, a dedicated Skyvern browser session is
created for each task and closed when that task finishes or is cancelled.
browser-use operates on an isolated local Chromium profile, including for
localhost sites, and uses its native ChatOpenAI adapter with the OpenAI key.
Choose browser-use for detailed diagnostics: observed page/console errors and
HTTP 404/5xx failures can fail a task even when the requested function works,
exposing other bugs in the app. Choose Skyvern for a broader functional check:
the requested flow passes when its expected outcome works, and unrelated console
errors, failed background requests or cosmetic issues do not fail the task.
The engine descriptions in Settings and Run Agent explain this distinction.

The desktop event pump receives worker messages through queues. Browsing and AI
calls run outside the Tk thread. Each selected task runs separately in a fresh
browser, with a limit of 100 agent steps and 15 minutes per task. Include all
required navigation and login prerequisites in each task's steps. A failed task
gets a FAILED verdict and the queue continues with the next task, including when
an engine raises an error. The overall run passes only if every task passes.
The result panel shows each task's verdict and failure details, and these results
are saved in history as `task_results`. Cancel stops the suite and labels remaining
tasks as not run due to cancellation.

The regression list and live log each expand to share the Run Agent page's
available height; the task list scrolls rather than squeezing other controls.
Use up/down arrows in
Regression Tasks or Run Agent to save a task order before launching. During a run,
the arrows reorder tasks that are still waiting; completed/running tasks stay in
place. Changing the live queue does not change the saved order for future runs.

For browser-use, an observed JavaScript/console error, HTTP 404 or HTTP 5xx fails
the current task with the URL, current agent step and error, then continues the
queue. Skyvern Cloud follows the test instructions and returns its structured
report; local browser diagnostic listeners do not attach to cloud runs.
Only a validated structured agent result can produce PASSED:

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
Each card has a selection checkbox. Select all selects the currently filtered
cards; Delete selected removes them from Home, the sidebar and saved history.
Deleting a waiting commit run also removes it from the pending queue. The active
run is protected until it finishes.
Home reuses existing run cards and groups rapid search input, keeping navigation,
filtering and status updates responsive as history grows.
History and Home refresh every 60 seconds, including relative timestamps, and
update immediately when a run starts or finishes or a commit arrives. This
refresh preserves form drafts and search/filter selections.
New manual runs never overwrite earlier results. Incoming commits cannot take
ownership of an already-running test's result.

Settings, selected tasks and up to 50 history entries live in `settings.json`,
`tasks.json` and `history.json` in the project directory, independently of the
working directory. The key field is masked; provider keys saved through Settings
are stored as plaintext in settings.json. Local state, credentials, environments and
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
The Skyvern smoke verifies the actual SDK's cloud API authentication using a
mock HTTP transport. These checks make no paid model calls. A full AI test requires your API key and
running target website.

API references used for the integrations:
[Skyvern SDK](https://github.com/Skyvern-AI/skyvern/blob/main/docs/sdk-reference/complete-reference.mdx),
[browser-use agent parameters](https://docs.browser-use.com/open-source/customize/agent/all-parameters),
[OpenAI GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna).
