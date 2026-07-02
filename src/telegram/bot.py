"""Jembatan Telegram — "satu otak, dua pintu masuk". Long-polling (requests, tanpa dependensi
tambahan), rute pesan dari chat_id yang diizinkan lewat pipeline chat_agent+skills yang SAMA
PERSIS dengan chat website (roster.system_prompt("orchestrator") + llm.orchestrator().chat_agent).
Histori disimpan di ChatSession yang SAMA (id="tg:<chat_id>") — obrolan Telegram & website
berbagi memori kalau chat_id dipakai konsisten (bukan wajib, tapi bonus alami dari arsitektur ini).

Jalankan:  python -m src.telegram.bot
Tak ada TELEGRAM_BOT_TOKEN → no-op graceful (exit bersih, tak crash, tak menghalangi web/dry-run).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import requests

from src import config

_API = "https://api.telegram.org/bot{token}/{method}"
_POLL_TIMEOUT = 25          # long-poll Telegram getUpdates (detik)
_MAX_LEN = 3900              # batas Telegram ~4096; sisakan margin


class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self._session = requests.Session()

    def _call(self, method: str, **params):
        url = _API.format(token=self.token, method=method)
        r = self._session.post(url, json=params, timeout=_POLL_TIMEOUT + 10)
        return r.json()

    def get_updates(self, offset: int | None = None):
        params = {"timeout": _POLL_TIMEOUT}
        if offset is not None:
            params["offset"] = offset
        data = self._call("getUpdates", **params)
        return data.get("result", []) if data.get("ok") else []

    def send_message(self, chat_id, text: str):
        """Kirim balasan, potong bila >batas Telegram, fallback ke plain text bila Markdown invalid."""
        for i in range(0, len(text), _MAX_LEN) or [0]:
            chunk = text[i:i + _MAX_LEN] or "(kosong)"
            resp = self._call("sendMessage", chat_id=chat_id, text=chunk, parse_mode="Markdown")
            if not resp.get("ok"):                      # markdown LLM sering tak valid utk Telegram parser
                self._call("sendMessage", chat_id=chat_id, text=chunk)


def _sid_for(chat_id) -> str:
    return f"tg:{chat_id}"[:40]


def _load_history(sid: str) -> list[dict]:
    from src.storage.db import SessionLocal
    from src.storage.models import ChatSession
    with SessionLocal() as s:
        r = s.get(ChatSession, sid)
        if not r:
            return []
        try:
            return json.loads(r.messages or "[]")
        except Exception:
            return []


def _save_history(sid: str, messages: list[dict]):
    from src.storage.db import SessionLocal
    from src.storage.models import ChatSession
    if not any(m.get("role") == "user" for m in messages):
        return
    title = next((m["content"] for m in messages if m.get("role") == "user"), "Sesi Telegram")[:160]
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        r = s.get(ChatSession, sid)
        if not r:
            r = ChatSession(id=sid, created=now)
            s.add(r)
        r.title = title
        r.messages = json.dumps(messages[-120:], ensure_ascii=False)
        r.n_messages = len(messages)
        r.updated = now
        s.commit()


def handle_message(bot: TelegramBot, chat_id, text: str):
    from src.agents import roster
    from src.llm import client as llm

    allowed = config.TELEGRAM_ALLOWED_CHAT_IDS
    if allowed and str(chat_id) not in allowed:
        bot.send_message(chat_id, f"Chat ID Anda: `{chat_id}`. Belum diotorisasi — minta admin "
                                   f"menambahkan ID ini ke TELEGRAM_ALLOWED_CHAT_IDS di .env.")
        return

    sid = _sid_for(chat_id)
    history = _load_history(sid)
    try:
        persona = roster.system_prompt("orchestrator")
    except Exception:
        persona = "Kamu Orin, Orchestrator crypto-smc-agent-system yang jujur & profesional."
    from src.web.app import _CHAT_SYS
    sysmsg = "\n\n".join([persona, _CHAT_SYS, "KONTEKS: pesan ini datang dari Telegram (bukan website)."])
    messages = [{"role": "system", "content": sysmsg}]
    for m in history[-8:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:2000]})
    messages.append({"role": "user", "content": text[:2000]})

    try:
        tools = roster.agent_tools_spec("orchestrator")
        impls = roster.agent_tool_impls("orchestrator")
        reply = llm.orchestrator(timeout=180).chat_agent(messages, tools, impls, max_steps=6, max_tokens=4000, temperature=0.3)
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] chat_agent error: {e}")
        reply = "Orin sedang tak bisa dihubungi. Coba lagi sebentar."

    reply = (reply or "").strip() or "(maaf, tak ada jawaban — coba ulangi)"
    bot.send_message(chat_id, reply)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    _save_history(sid, history)


def run():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("[telegram] TELEGRAM_BOT_TOKEN kosong — bot tidak start (fitur opsional, sisa sistem tak terganggu).")
        return
    bot = TelegramBot(token)
    me = bot._call("getMe")
    if not me.get("ok"):
        print(f"[telegram] token tak valid: {me}")
        return
    print(f"[telegram] bot aktif: @{me['result'].get('username')}")
    offset = None
    while True:
        try:
            updates = bot.get_updates(offset)
        except Exception as e:  # noqa: BLE001
            print(f"[telegram] poll error: {e}")
            time.sleep(5)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip()
            chat_id = (msg.get("chat") or {}).get("id")
            if not text or chat_id is None:
                continue
            try:
                handle_message(bot, chat_id, text)
            except Exception as e:  # noqa: BLE001
                print(f"[telegram] handle_message error: {e}")
                try:
                    bot.send_message(chat_id, "Terjadi kesalahan internal. Coba lagi.")
                except Exception:
                    pass


if __name__ == "__main__":
    run()
