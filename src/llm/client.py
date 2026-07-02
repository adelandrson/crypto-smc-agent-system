"""Klien LLM lokal (OpenAI-compatible) — otak orchestrator & agent.

Menangani model reasoning (mis. minimax-m3 yang keluarkan <think>…</think>): blok think
dibuang dari output. Dua tier: orchestrator (reasoning kuat) & light (agent ringan).
"""
import json
import re

import requests

from src import config

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_OPEN = re.compile(r"<think>.*$", re.DOTALL)
_JSON = re.compile(r"\{.*\}", re.DOTALL)


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: int = 180):
        self.model = model or config.LLM_MODEL_ORCH
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._s = requests.Session()

    def chat(self, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.0, _depth: int = 0) -> str:
        if not self.base_url or not self.model:
            raise LLMError("LLM belum dikonfigurasi — set LLM_BASE_URL & LLM_MODEL_ORCH di .env "
                           "(atau atur lewat Hermes framework). LLM bersifat opsional.")
        try:
            r = self._s.post(
                f"{self.base_url}/chat/completions",
                json={"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(f"network: {exc}")
        if not r.ok:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        txt = r.content.decode("utf-8", errors="replace").strip()  # paksa UTF-8 (hindari mojibake)
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            try:                                   # endpoint kadang kirim objek + data ekstra (mis. SSE 'data: [DONE]')
                data, _ = json.JSONDecoder().raw_decode(txt)
            except json.JSONDecodeError:
                raise LLMError(f"respons non-JSON: {txt[:200]}")
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"respons tak terduga: {txt[:200]}")
        finish = choice.get("finish_reason")
        content = _THINK.sub("", content)        # buang reasoning tertutup
        content = _THINK_OPEN.sub("", content)   # buang think tak tertutup (kehabisan token)
        content = content.strip()
        # SELF-HEAL truncation (finish_reason='length') — penyebab utama 'stop mendadak' / 'kepotong' di model reasoning.
        if finish == "length" and _depth < 2:
            if not content:
                # habis token di <think> → jawaban KOSONG → paksa jawab langsung, budget lebih besar
                m2 = list(messages) + [{"role": "user",
                    "content": "Jawab LANGSUNG & to-the-point sekarang — JANGAN tulis blok reasoning/<think> panjang."}]
                return self.chat(m2, max_tokens=max(max_tokens, 4000), temperature=temperature, _depth=_depth + 1)
            # terpotong di tengah JAWABAN → sambung dari titik terakhir lalu gabung (anti 'kepotong')
            m2 = list(messages) + [{"role": "assistant", "content": content},
                {"role": "user", "content": "Lanjutkan jawaban dari titik terakhir tadi — jangan ulang yang sudah ditulis."}]
            cont = self.chat(m2, max_tokens=max_tokens, temperature=temperature, _depth=_depth + 1)
            return (content + ("\n" + cont if cont else "")).strip()
        return content

    def _post(self, payload: dict) -> dict:
        try:
            r = self._s.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"network: {exc}")
        if not r.ok:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        txt = r.content.decode("utf-8", errors="replace").strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            try:
                data, _ = json.JSONDecoder().raw_decode(txt)
                return data
            except json.JSONDecodeError:
                raise LLMError(f"respons non-JSON: {txt[:200]}")

    def chat_agent(self, messages: list[dict], tools: list[dict], tool_impls: dict,
                   max_steps: int = 6, max_tokens: int = 1800, temperature: float = 0.0,
                   on_tool=None) -> str:
        """Loop AGENT (function-calling): LLM boleh panggil tools (skills) berulang sampai cukup,
        lalu susun jawaban final. tool_impls: {name: callable(**args)->jsonable}. on_tool(name,args) callback opsional."""
        if not self.base_url or not self.model:
            raise LLMError("LLM belum dikonfigurasi — set LLM_BASE_URL & LLM_MODEL_ORCH di .env.")
        msgs = list(messages)
        for _ in range(max_steps):
            data = self._post({"model": self.model, "messages": msgs, "max_tokens": max_tokens,
                               "temperature": temperature, "tools": tools, "tool_choice": "auto"})
            try:
                msg = data["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                raise LLMError(f"respons tak terduga: {json.dumps(data)[:200]}")
            calls = msg.get("tool_calls") or []
            if not calls:
                c = _THINK.sub("", msg.get("content") or "")
                c = _THINK_OPEN.sub("", c).strip()
                if c:
                    return c
                break                              # konten kosong (truncated mid-<think>) → ke forced-final
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for tc in calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if on_tool:
                    try:
                        on_tool(name, args)
                    except Exception:
                        pass
                impl = tool_impls.get(name)
                try:
                    result = impl(**args) if impl else {"error": f"tool tak dikenal: {name}"}
                except Exception as e:
                    result = {"error": str(e)[:200]}
                msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "name": name,
                             "content": json.dumps(result, default=str, ensure_ascii=False)[:4000]})
        # kehabisan langkah / konten kosong → paksa jawaban final tanpa tool (chat() self-heal kalau truncated)
        msgs.append({"role": "user", "content": "Cukup memanggil tool. Susun jawaban FINAL sekarang dari hasil tool "
                     "di atas — LANGSUNG & to-the-point, JANGAN tulis blok reasoning/<think> panjang."})
        return self.chat(msgs, max_tokens=max(max_tokens, 4000))

    def chat_json(self, messages: list[dict], max_tokens: int = 1500) -> dict:
        msgs = [{"role": "system", "content": "Jawab HANYA dengan satu objek JSON valid, tanpa teks/markdown lain."}] + messages
        txt = self.chat(msgs, max_tokens=max_tokens)
        m = _JSON.search(txt)
        if not m:
            raise LLMError(f"tak ada JSON di respons: {txt[:150]}")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON invalid: {exc} | {txt[:150]}")


def orchestrator(timeout: int = 90) -> LLM:
    return LLM(config.LLM_MODEL_ORCH, timeout=timeout)   # default 90s; chat agentik pakai lebih lama (token besar = lambat)


def light() -> LLM:
    return LLM(config.LLM_MODEL_LIGHT, timeout=60)
