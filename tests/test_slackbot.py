import json
from pathlib import Path

import pytest

from risktool import slack_format as fmt
from risktool.pipeline import BuildResult, CompileError
from risktool.sheets import Sheet, SheetFormatError
from risktool.slackbot import BuildService, register
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


def report(errors=(), warnings=(), mode="final"):
    r = Report(mode)
    r.errors, r.warnings = list(errors), list(warnings)
    return r


def service(client, run_build=None, fetch_sheet=None):
    return BuildService(
        client, "C1", "SHEET",
        fetch_sheet=fetch_sheet or (lambda: Sheet({}, GIDS)),
        run_build=run_build or (lambda grids, mode, out: BuildResult(report(mode=mode), out)),
    )


def test_successful_build_uploads_pdf_in_thread():
    c = FakeClient()
    s = service(c)
    s.submit("final", "U1")
    s.run_pending()
    post = c.of("post")[0]
    assert "<@U1> started a *Final* build" in post["text"]
    upload = c.of("upload")[0]
    assert upload["thread_ts"] == "100.1" and upload["filename"] == "risk-assessment-final.pdf"
    assert "Here's the PDF." in upload["initial_comment"]
    assert ":white_check_mark:" in c.of("update")[-1]["text"]


def test_invalid_sheet_lists_problems_with_row_links():
    c = FakeClient()
    err = Issue("Risks", "residual risk is Unacceptable", 15, "RK_011")
    warn = Issue("Hazards", "hazard has no risks", 5, "HZ_002")
    s = service(c, run_build=lambda g, m, o: BuildResult(report([err], [warn]), None))
    s.submit("final", "U1")
    s.run_pending()
    reply = c.of("post")[1]
    assert reply["thread_ts"] == "100.1"
    assert ("*<https://docs.google.com/spreadsheets/d/SHEET/edit#gid=44&range=A15|"
            "Risks row 15 (RK_011)>*: residual risk is Unacceptable") in reply["text"]
    assert "gid=11&range=A5" in reply["text"]
    assert "run `/risk final` again" in reply["text"]
    assert c.of("upload") == []
    assert "1 problem to fix" in c.of("update")[-1]["text"]


def test_long_lists_are_cut_and_attached():
    c = FakeClient()
    errs = [Issue("Risks", f"problem {i}", i, f"RK_{i:03}") for i in range(40)]
    s = service(c, run_build=lambda g, m, o: BuildResult(report(errs), None))
    s.submit("final", "U1")
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
    s.submit("pdr", "U1")
    s.run_pending()
    reply = c.of("post")[1]["text"]
    assert phrase in reply and "secret internals" not in reply
    assert "couldn't run" in c.of("update")[-1]["text"]


def test_second_build_queues_behind_the_first():
    c = FakeClient()
    s = service(c)
    s.submit("final", "U1")
    s.submit("pdr", "U2")
    assert "queued behind <@U1>" in c.of("post")[1]["text"]
    s.run_pending()
    updates = [u["text"] for u in c.of("update") if u["ts"] == "100.2"]
    assert "started a *PDR* build" in updates[0]
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
    acks, c, _ = invoke("")
    assert acks[0]["response_type"] == "ephemeral" and "/risk final" in acks[0]["text"]
    assert c.calls == []


def test_unknown_option():
    acks, _, _ = invoke("publish")
    assert "I don't know `/risk publish`" in acks[0]["text"]


def test_wrong_channel_is_refused_privately():
    acks, c, _ = invoke("final", channel="C9")
    assert "only works in <#C1>" in acks[0]["text"] and c.calls == []


def test_valid_command_queues_a_build():
    acks, c, s = invoke(" Final ")
    assert acks == [{}]
    assert s.jobs.qsize() == 1 and "started a *Final* build" in c.of("post")[0]["text"]


# ---- End to end with the real pipeline -------------------------------------

def test_real_build_from_sample_sheet(tmp_path):
    from risktool.pipeline import build

    grids = json.loads((ROOT / "examples/sample-sheet.json").read_text())
    c = FakeClient()
    s = service(c, fetch_sheet=lambda: Sheet(grids, GIDS),
                run_build=lambda g, m, out: build(g, m, ROOT, out))
    s.submit("final", "U1")
    s.run_pending()
    upload = c.of("upload")[0]
    assert Path(upload["file"]).name == "risk-assessment-final.pdf"
    assert ":white_check_mark:" in c.of("update")[-1]["text"]
