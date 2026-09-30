import pytest

from risktool.drive import FOLDER_NAME, Drive, DriveError


class Resp:
    def __init__(self, status, body):
        self.status_code, self.body = status, body
        self.ok = status < 400

    def json(self):
        return self.body


def quota_error():
    return Resp(403, {"error": {"message": "Service Accounts do not have storage quota.",
                                "errors": [{"reason": "storageQuotaExceeded"}]}})


class FakeSession:
    """Answers Drive calls from a table of (method, url suffix, query fragment) → response."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, params=None, **kw):
        self.calls.append((method, url, params, kw))
        for (m, suffix, fragment), resp in self.routes:
            if m == method and url.endswith(suffix) and fragment in (params or {}).get("q", ""):
                return resp
        raise AssertionError(f"unexpected {method} {url} {params}")


def folder_routes(folders, sheet_parents=("P",)):
    return [
        (("GET", "/files/SHEET", ""), Resp(200, {"parents": list(sheet_parents)})),
        (("GET", "/files", FOLDER_NAME), Resp(200, {"files": folders})),
    ]


def test_finds_the_folder_beside_the_sheet():
    d = Drive(FakeSession(folder_routes([{"id": "F1", "parents": ["X"]},
                                         {"id": "F2", "parents": ["P"]}])))
    assert d.find_folder("SHEET") == "F2"


def test_falls_back_to_the_only_visible_folder():
    # The bot may be shared on the PDF folder but not on the sheet's folder.
    d = Drive(FakeSession(folder_routes([{"id": "F1", "parents": ["X"]}], sheet_parents=())))
    assert d.find_folder("SHEET") == "F1"


@pytest.mark.parametrize("folders, phrase", [
    ([], "no 'published risk assessment' folder"),
    ([{"id": "F1", "parents": ["X"]}, {"id": "F2", "parents": ["Y"]}], "RISK_DRIVE_FOLDER_ID"),
])
def test_folder_problems(folders, phrase):
    with pytest.raises(DriveError, match=phrase):
        Drive(FakeSession(folder_routes(folders))).find_folder("SHEET")


def test_replaces_the_existing_file(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF new")
    s = FakeSession([
        (("GET", "/files", "Risk assessment (Final).pdf"), Resp(200, {"files": [{"id": "PDF1"}]})),
        (("PATCH", "/files/PDF1", ""), Resp(200, {"webViewLink": "https://drive/PDF1"})),
    ])
    assert Drive(s).publish(pdf, "final", "F1") == "https://drive/PDF1"
    method, url, params, kw = s.calls[-1]
    assert "/upload/" in url and params["uploadType"] == "media"
    assert kw["data"] == b"%PDF new"
    assert "'F1' in parents" in s.calls[0][2]["q"]


def test_creates_the_file_when_missing(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    s = FakeSession([
        (("GET", "/files", "(PDR)"), Resp(200, {"files": []})),
        (("POST", "/files", ""), Resp(200, {"webViewLink": "https://drive/new"})),
    ])
    assert Drive(s).publish(pdf, "pdr", "F1") == "https://drive/new"
    body = s.calls[-1][3]["data"]
    assert b'"parents": ["F1"]' in body and b"%PDF" in body


def test_my_drive_create_explains_the_placeholder(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    s = FakeSession([
        (("GET", "/files", "(PDR)"), Resp(200, {"files": []})),
        (("POST", "/files", ""), quota_error()),
    ])
    with pytest.raises(DriveError, match=r"Upload any PDF named 'Risk assessment \(PDR\)\.pdf'"):
        Drive(s).publish(pdf, "pdr", "F1")


def test_other_errors_name_the_status():
    s = FakeSession([(("GET", "/files/SHEET", ""), Resp(404, {"error": {
        "errors": [{"reason": "notFound"}]}}))])
    with pytest.raises(DriveError, match=r"\(404 notFound\)"):
        Drive(s).find_folder("SHEET")
