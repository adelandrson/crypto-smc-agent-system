"""Test src/telegram/bot.py — logika murni (allowlist, sesi ChatSession), tanpa panggilan
Telegram API nyata (TelegramBot._call/send_message di-stub)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src import config
from src.storage.models import Base, ChatSession
from src.telegram import bot as tg


def _mk_session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)


class FakeBot:
    """Stub TelegramBot — tangkap pesan yg dikirim tanpa hit API nyata."""
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_sid_for_prefixes_and_caps_length():
    assert tg._sid_for(12345) == "tg:12345"
    assert tg._sid_for("x" * 100).startswith("tg:")
    assert len(tg._sid_for("x" * 100)) == 40


def test_allowlist_rejects_unlisted_chat_id(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_CHAT_IDS", {"111"})
    fb = FakeBot()
    tg.handle_message(fb, 999, "halo")
    assert len(fb.sent) == 1
    assert "999" in fb.sent[0][1] and "Belum diotorisasi" in fb.sent[0][1]


def test_allowlist_empty_means_open(monkeypatch):
    """TELEGRAM_ALLOWED_CHAT_IDS kosong = belum dikonfigurasi -> tak menolak siapa pun (dev/first-run)."""
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_CHAT_IDS", set())
    Mk = _mk_session()
    monkeypatch.setattr("src.storage.db.SessionLocal", Mk)

    class FakeRoster:
        @staticmethod
        def system_prompt(agent): return "persona"
        @staticmethod
        def agent_tools_spec(agent): return []
        @staticmethod
        def agent_tool_impls(agent): return {}

    class FakeLLMInst:
        def chat_agent(self, *a, **k): return "jawaban tes"

    class FakeLLM:
        @staticmethod
        def orchestrator(timeout=180): return FakeLLMInst()

    monkeypatch.setattr("src.agents.roster", FakeRoster)
    monkeypatch.setattr("src.llm.client", FakeLLM)
    monkeypatch.setattr("src.web.app._CHAT_SYS", "sys")

    fb = FakeBot()
    tg.handle_message(fb, 42, "halo Orin")
    assert len(fb.sent) == 1
    assert fb.sent[0] == (42, "jawaban tes")

    with Mk() as s:
        row = s.get(ChatSession, "tg:42")
        assert row is not None
        assert row.n_messages == 2   # user + assistant
        assert "halo Orin" in row.title


def test_load_save_history_roundtrip(monkeypatch):
    Mk = _mk_session()
    monkeypatch.setattr("src.storage.db.SessionLocal", Mk)
    sid = "tg:777"
    assert tg._load_history(sid) == []
    tg._save_history(sid, [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
    assert tg._load_history(sid) == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]


def test_save_history_skips_greeting_only(monkeypatch):
    Mk = _mk_session()
    monkeypatch.setattr("src.storage.db.SessionLocal", Mk)
    sid = "tg:888"
    tg._save_history(sid, [{"role": "assistant", "content": "halo saja"}])
    with Mk() as s:
        assert s.get(ChatSession, sid) is None
