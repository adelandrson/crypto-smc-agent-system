"""Test wewenang penuh agent: write_source scoping (izinkan src/tests, blokir rahasia/deploy)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.llm import skills


def test_write_source_blocks_secrets_and_outside(tmp_path, monkeypatch):
    # .env / secrets / db / di luar src|tests DITOLAK
    assert "error" in skills.write_source(".env", "X=1")
    assert "error" in skills.write_source("secrets.py", "x=1")           # nama mengandung 'secret'
    assert "error" in skills.write_source("crypto_smc.db", "x")
    assert "error" in skills.write_source("run_services.sh", "rm -rf /")  # skrip deploy di luar src/tests
    assert "error" in skills.write_source("../etc/passwd", "x")           # path traversal
    assert "error" in skills.write_source("src/smc/x.exe", "x")           # ekstensi tak diizinkan


def test_write_source_allows_code_then_reverts(tmp_path):
    # tulis file .py sementara di src/, verifikasi, lalu hapus (jangan kotori repo)
    rel = "src/smc/_authority_probe.py"
    r = skills.write_source(rel, "# probe wewenang\nX = 42\n")
    assert r.get("ok") and r["path"].endswith("_authority_probe.py")
    import os
    root = os.path.abspath(os.path.join(os.path.dirname(skills.__file__), "..", ".."))
    full = os.path.join(root, rel)
    assert os.path.isfile(full) and "X = 42" in open(full).read()
    os.remove(full)                                                       # bersihkan


def test_write_source_and_run_tests_registered():
    impls = skills.tool_impls()
    assert "write_source" in impls and "run_tests" in impls
    spec_names = {t["function"]["name"] for t in skills.tools_spec()}
    assert {"write_source", "run_tests", "config_set"} <= spec_names
