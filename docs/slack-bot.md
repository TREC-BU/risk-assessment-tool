# Slack bot

Lets anyone in one Slack channel build the risk assessment PDF from the live
Google Sheet. Nobody needs anything installed on their own computer.

- `/risk pdr` builds the Preliminary Design Review document.
- `/risk` or `/risk final` builds the complete document.
- `/risk help` shows the commands (only to the person who asked).

The bot posts a status message, edits it as the build runs, and replies in its
thread with the PDF or with the problems to fix. Each problem links to its row
in the sheet. Builds run one at a time; a second request waits and says so.

Each successful build also replaces that mode's PDF in the Google Drive folder
next to the sheet, and the thread links to it.

The bot runs on the server in Docker and connects out to Slack (Socket Mode),
so the server needs no public URL, domain or open port.

## One-time setup

### 1. Create the Slack app

1. Go to https://api.slack.com/apps → **Create New App** → **From an app
   manifest**. Pick your workspace and paste in `slack-manifest.yaml`.
2. **Basic Information → App-Level Tokens → Generate Token and Scopes**. Name
   it `socket`, add the `connections:write` scope and generate. Copy the
   `xapp-…` token.
3. **Install App → Install to Workspace**. Copy the **Bot User OAuth Token**
   (`xoxb-…`).
4. In Slack, create the channel (e.g. `#risk-assessment`) and run
   `/invite @Risk Bot` in it.
5. Get the channel ID: right-click the channel → **View channel details**;
   the ID (`C…`) is at the bottom.

### 2. Put the code and secrets on the server

The server needs Docker with the compose plugin.

```sh
git clone <this repo> risk-assessment-tool
cd risk-assessment-tool
mkdir secrets fonts
```

Create `secrets/slack.env`:

```sh
SLACK_BOT_TOKEN=xoxb-…
SLACK_APP_TOKEN=xapp-…
RISK_SLACK_CHANNEL=C…
```

Copy the Google service account key (the same one the CLI uses) to
`secrets/google-key.json`. From your Mac:

```sh
scp ~/.config/gspread/account_credentials.json server:risk-assessment-tool/secrets/google-key.json
```

`RISK_SHEET_ID` is already in the committed `.env`.

### 3. Copy Helvetica Neue from a Mac

The template's body font is licensed with macOS, so it isn't in the image or
the repo. Copy it to the server once:

```sh
scp /System/Library/Fonts/HelveticaNeue.ttc server:risk-assessment-tool/fonts/
```

Arial (Microsoft's free core fonts) and Raleway (open source) are downloaded
into the image when it's built. The bot checks all three fonts at startup and
refuses to run without them, so a
missing font can't silently change the layout.

### 4. Google Drive copy

Successful builds replace `Risk assessment (PDR).pdf` or
`Risk assessment (Final).pdf` in a folder named **published risk assessment**,
kept in the same folder as the sheet. The links never change, and Drive keeps
each earlier build under **Manage versions**.

1. Enable the Google Drive API in the service account's Cloud project.
2. Create the folder and share it with the service account's email as
   **Editor**.
3. If the folder is in someone's My Drive (not a Shared Drive), upload any PDF
   under each of the two names once. The service account has no Drive storage
   of its own, so it can replace these files but can't create them. In a
   Shared Drive it creates them itself.

To use a different folder, put its ID (the part of the folder URL after
`folders/`) in `.env` as `RISK_DRIVE_FOLDER_ID`.

If the Drive upload fails, the bot still posts the PDF in Slack and says why
the Drive copy wasn't updated.

### 5. Start it

```sh
docker compose up -d --build
docker compose logs -f        # should end with "listening for /risk in C…"
```

It restarts on its own after a crash or a server reboot.

### 6. Automatic deploys

`.github/workflows/deploy.yml` redeploys on every push to `main`. It needs SSH
access from GitHub's runners to the server (port 22 open to the internet).

Make a key used only for deploys, and allow it on the server:

```sh
ssh-keygen -t ed25519 -N '' -f deploy_key -C github-deploy
ssh-copy-id -i deploy_key.pub server
ssh-keyscan -t ed25519 <server host> > known_hosts
```

Add these repository secrets (**Settings → Secrets and variables → Actions**):

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH user that owns `~/risk-assessment-tool` and can run `docker` |
| `DEPLOY_SSH_KEY` | Contents of `deploy_key` (the private key) |
| `DEPLOY_KNOWN_HOSTS` | Contents of `known_hosts` |

Then delete the local `deploy_key` files. The server's clone must be able to
`git fetch` on its own: clone over HTTPS if the repo is public, or add a
read-only deploy key to the repo if it's private.

## Day to day

- **Update after changing the code or template:** push to `main`. The Deploy
  workflow runs the tests, then SSHes in and runs
  `git reset --hard origin/main && docker compose up -d --build`. Any edits made
  directly on the server to tracked files are overwritten; `secrets/` and
  `fonts/` are git-ignored and left alone. To deploy by hand:
  `git pull && docker compose up -d --build`
- **Logs:** `docker compose logs --tail 100`. Full error details go here, not
  to Slack.
- **Stop:** `docker compose down`

## Troubleshooting

| Slack says | Fix |
| --- | --- |
| "I'm not in this channel yet" | `/invite @Risk Bot` in the channel. |
| "`/risk` only works in #…" | Use the configured channel, or change `RISK_SLACK_CHANNEL`. |
| "the bot can't open the Google Sheet" | Share the sheet with the service account's email (Viewer). |
| "the sheet has no tab named '…'" | A tab was renamed; the four tabs must be Hazards, Situations, Mitigations, Risks. |
| "the PDF compiler failed" | Check the logs; usually a template edit that doesn't compile. |
| `/risk` gives "dispatch_failed" | The bot isn't running: `docker compose ps`, then check the logs. |
| "no 'published risk assessment' folder shared with the bot" | Share the folder with the service account as Editor, or set `RISK_DRIVE_FOLDER_ID`. |
| "can't create files in a My Drive folder" | Upload a PDF with the name it gives to the folder once (see setup step 4). |
