import os

from risktool.cli import load_dotenv


def test_load_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nRISK_SHEET_ID=abc123\nexport QUOTED="x y"\nKEEP=from-file\n\n')
    monkeypatch.delenv("RISK_SHEET_ID", raising=False)
    monkeypatch.delenv("QUOTED", raising=False)
    monkeypatch.setenv("KEEP", "from-env")
    load_dotenv(env)
    assert os.environ["RISK_SHEET_ID"] == "abc123"
    assert os.environ["QUOTED"] == "x y"
    assert os.environ["KEEP"] == "from-env"


def test_missing_dotenv_is_ignored(tmp_path):
    load_dotenv(tmp_path / ".env")
