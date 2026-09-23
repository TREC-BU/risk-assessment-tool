# Slack bot

Lets anyone in one Slack channel build the risk assessment PDF from the live
Google Sheet. Nobody needs anything installed on their own computer.

- `/risk pdr` builds the Preliminary Design Review document.
- `/risk final` builds the complete document.
- `/risk help` shows the commands (only to the person who asked).

The bot posts a status message, edits it as the build runs, and replies in its
thread with the PDF or with the problems to fix. Each problem links to its row
in the sheet. Builds run one at a time; a second request waits and says so.

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

### 4. Start it

```sh
docker compose up -d --build
docker compose logs -f        # should end with "listening for /risk in C…"
```

It restarts on its own after a crash or a server reboot.

## Day to day

- **Update after changing the code or template:**
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
