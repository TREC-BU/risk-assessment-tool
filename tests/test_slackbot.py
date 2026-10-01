import json
from pathlib import Path

import pytest

from risktool import slack_format as fmt
from risktool.drive import DriveError
from risktool.pipeline import BuildResult, CompileError
from risktool.sheets import Sheet, SheetFormatError
from risktool.slackbot import BuildService, announce_version, register
from risktool.validate import Issue, Report

ROOT = Path(__file__).resolve().parents[1]
GIDS = {"Hazards": 11, "Situations": 22, "Mitigations": 33, "Risks": 44}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.n = 0

    def chat_postMessage(self, **kw):
        self.n += 1
        self.calls.append(("post", kw))
        return {"ts": f"100.{self.n}"}

    def chat_update(self, **kw):
        self.calls.append(("update", kw))

    def files_upload_v2(self, **kw):
        self.calls.append(("upload", kw))

    def of(self, kind):
        return [kw for k, kw in self.calls if k == kind]


def report(errors=(), warnings=(), info=()):
    return Report(list(errors), list(warnings), list(info))


def service(client, run_build=None, fetch_sheet=None, publish=None):
    return BuildService(
        client, "C1", "SHEET",
        fetch_sheet=fetch_sheet or (lambda: Sheet({}, GIDS)),
        run_build=run_build or (lambda grids, out: BuildResult(report(), out)),
        publish=publish,
    )


def test_successful_build_uploads_pdf_in_thread():
    c = FakeClient()
    s = service(c)
    s.submit("U1")
    s.run_pending()
    post = c.of("post")[0]
    assert "<@U1> started a build" in post["text"]
    upload = c.of("upload")[0]
    assert upload["thread_ts"] == "100.1" and upload["filename"] == "risk-assessment.pdf"
    assert "Here's the PDF." in upload["initial_comment"]
    assert ":white_check_mark:" in c.of("update")[-1]["text"]


def test_successful_build_links_the_drive_copy():
    c, published = FakeClient(), []

    def publish(pdf):
        published.append(pdf.name)
        return "https://drive/PDF1"

    s = service(c, publish=publish)
    s.submit("U1")
    s.run_pending()
    assert published == ["risk-assessment.pdf"]
    assert "<https://drive/PDF1|The copy in Google Drive> is updated." in c.of("upload")[0]["initial_comment"]


@pytest.mark.parametrize("exc, phrase", [
    (DriveError("there's no 'published risk assessment' folder shared with the bot."), "no 'published risk assessment' folder"),
    (RuntimeError("secret internals"), "something unexpected"),
])
def test_drive_failure_still_posts_the_pdf(exc, phrase):
    c = FakeClient()

    def publish(pdf):
        raise exc

    s = service(c, publish=publish)
    s.submit("U1")
    s.run_pending()
    comment = c.of("upload")[0]["initial_comment"]
    assert "Couldn't update the copy in Google Drive" in comment and phrase in comment
    assert "secret internals" not in comment
    assert ":white_check_mark:" in c.of("update")[-1]["text"]


def test_invalid_build_is_not_published():
    c, published = FakeClient(), []
    err = Issue("Risks", "hazard_id 'HZ_404' is not on the Hazards tab", 15, "RK_011")
    s = service(c, run_build=lambda g, o: BuildResult(report([err]), None),
                publish=lambda pdf: published.append(pdf))
    s.submit("U1")
    s.run_pending()
    assert published == []


def test_invalid_sheet_lists_problems_with_row_links():
    c = FakeClient()
    err = Issue("Risks", "hazard_id 'HZ_404' is not on the Hazards tab", 15, "RK_011")
    info = Issue("Hazards", "hazard has no risks", 5, "HZ_002")
    s = service(c, run_build=lambda g, o: BuildResult(report([err], info=[info]), None))
    s.submit("U1")
    s.run_pending()
    reply = c.of("post")[1]
    assert reply["thread_ts"] == "100.1"
    assert ("*<https://docs.google.com/spreadsheets/d/SHEET/edit#gid=44&range=A15|"
            "Risks row 15 (RK_011)>*: hazard_id 'HZ_404' is not on the Hazards tab") in reply["text"]
    assert ":information_source: *1 info*" in reply["text"] and "gid=11&range=A5" in reply["text"]
    assert "run `/risk` again" in reply["text"]
    assert c.of("upload") == []
    assert "1 error to fix" in c.of("update")[-1]["text"]


def test_warnings_do_not_stop_the_build():
    c = FakeClient()
    warn = Issue("Risks", "residual risk is Unacceptable", 15, "RK_011")
    s = service(c, run_build=lambda g, o: BuildResult(report(warnings=[warn]), o))
    s.submit("U1")
    s.run_pending()
    comment = c.of("upload")[0]["initial_comment"]
    assert "Here's the PDF." in comment and ":warning: *1 warning*" in comment
    assert "residual risk is Unacceptable" in comment
    assert "PDF in thread (1 warning)." in c.of("update")[-1]["text"]


def test_long_lists_are_cut_and_attached():
    c = FakeClient()
    errs = [Issue("Risks", f"problem {i}", i, f"RK_{i:03}") for i in range(40)]
    s = service(c, run_build=lambda g, o: BuildResult(report(errs), None))
    s.submit("U1")
    s.run_pending()
    reply = c.of("post")[1]["text"]
    assert reply.count("\n• ") <= fmt.MAX_LINES
    assert "full list is attached" in reply
    attached = c.of("upload")[0]
    assert attached["filename"] == "problems.txt" and "problem 39" in attached["content"]


@pytest.mark.parametrize("exc, phrase", [
    (SheetFormatError("the sheet has no tab named 'Risks'"), "no tab named 'Risks'"),
    (CompileError("boom"), "PDF compiler failed"),
    (RuntimeError("secret internals"), "something unexpected"),
])
def test_failures_are_reported_plainly(exc, phrase):
    c = FakeClient()

    def explode():
        raise exc

    s = service(c, fetch_sheet=explode)
    s.submit("U1")
    s.run_pending()
    reply = c.of("post")[1]["text"]
    assert phrase in reply and "secret internals" not in reply
    assert "couldn't run" in c.of("update")[-1]["text"]


def test_second_build_queues_behind_the_first():
    c = FakeClient()
    s = service(c)
    s.submit("U1")
    s.submit("U2")
    assert "queued behind <@U1>" in c.of("post")[1]["text"]
    s.run_pending()
    updates = [u["text"] for u in c.of("update") if u["ts"] == "100.2"]
    assert "<@U2> started a build" in updates[0]
    assert ":white_check_mark:" in updates[-1]


def test_escapes_slack_control_characters():
    err = Issue("Risks", "event <script> & stuff", 5, "RK_001")
    text, _ = fmt.result(report([err]), "SHEET", GIDS)
    assert "&lt;script&gt; &amp; stuff" in text


# ---- Command routing -------------------------------------------------------

class FakeApp:
    def command(self, name):
        def deco(fn):
            self.handler = fn
            return fn
        return deco


def invoke(text, channel="C1"):
    app, c = FakeApp(), FakeClient()
    s = service(c)
    register(app, s, "C1")
    acks = []
    app.handler(ack=lambda **kw: acks.append(kw),
                command={"text": text, "channel_id": channel, "user_id": "U1"},
                respond=lambda **kw: acks.append(kw))
    return acks, c, s


def test_help_is_private():
    acks, c, _ = invoke("help")
    assert acks[0]["response_type"] == "ephemeral" and "`/risk` builds" in acks[0]["text"]
    assert c.calls == []


def test_unknown_option():
    acks, _, _ = invoke("publish")
    assert "I don't know `/risk publish`" in acks[0]["text"]


def test_wrong_channel_is_refused_privately():
    acks, c, _ = invoke("", channel="C9")
    assert "only works in <#C1>" in acks[0]["text"] and c.calls == []


def test_bare_command_queues_a_build():
    acks, c, s = invoke(" ")
    assert acks == [{}]
    assert s.jobs.qsize() == 1 and "started a build" in c.of("post")[0]["text"]


def test_old_mode_names_are_unknown():
    acks, _, s = invoke("final")
    assert "I don't know `/risk final`" in acks[0]["text"] and s.jobs.qsize() == 0


# ---- Deploy announcement ---------------------------------------------------

DEPLOY_ENV = {
    "RISK_COMMIT_SHA": "0123456789abcdef",
    "RISK_COMMIT_AUTHOR": "Sam <Lee>",
    "RISK_COMMIT_MESSAGE": ("Add Drive upload\n\nReplaces the PDF\nafter each build.\n\n"
                            "Co-Authored-By: Claude <noreply@anthropic.com>\n"),
    "RISK_REPO_URL": "https://github.com/org/repo",
}


def test_deploy_is_announced_once(tmp_path):
    c, marker = FakeClient(), tmp_path / "build" / "announced-commit"
    announce_version(c, "C1", DEPLOY_ENV, marker)
    text = c.of("post")[0]["text"]
    assert text.startswith(":rocket: Updated to <https://github.com/org/repo/commit/0123456789abcdef|0123456>")
    assert "by Sam &lt;Lee&gt;: *Add Drive upload*" in text
    assert text.endswith("*Add Drive upload*\n> Replaces the PDF\n> after each build.")
    # A restart of the same container doesn't repeat it.
    announce_version(c, "C1", DEPLOY_ENV, marker)
    assert len(c.of("post")) == 1


def test_no_announcement_without_a_deploy(tmp_path):
    c = FakeClient()
    announce_version(c, "C1", {}, tmp_path / "announced-commit")
    assert c.calls == []


def test_announcement_without_repo_or_body():
    text = fmt.deployed("0123456789abcdef", "Sam", "Fix typo\n", None)
    assert text == ":rocket: Updated to `0123456` by Sam: *Fix typo*"


# ---- End to end with the real pipeline -------------------------------------

def test_real_build_from_sample_sheet(tmp_path):
    from risktool.pipeline import build

    grids = json.loads((ROOT / "examples/sample-sheet.json").read_text())
    c = FakeClient()
    s = service(c, fetch_sheet=lambda: Sheet(grids, GIDS),
                run_build=lambda g, out: build(g, ROOT, out))
    s.submit("U1")
    s.run_pending()
    upload = c.of("upload")[0]
    assert Path(upload["file"]).name == "risk-assessment.pdf"
    assert ":white_check_mark:" in c.of("update")[-1]["text"]
