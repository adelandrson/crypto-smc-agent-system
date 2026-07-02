"""Roster Orchestrator + divisi kecil: identitas, spesialisasi, tugas, SKILL tiap agent.

Pola SAMA PERSIS dengan crypto-trader-agent-system (src/agents/roster.py): system_prompt(agent)
menyusun KONSTITUSI bersama (agents/IDENTITY.md+SOUL.md+USER.md+MEMORY.md) + peran spesifik +
skill yang dimiliki jadi satu system-prompt. Roster LEBIH KECIL (5 vs 11) karena metodologi
sumber tak punya fitur fundamentals/onchain/news/unlock (sengaja dikecualikan, lihat plan).
"""
import os
from functools import lru_cache

_DOC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "agents"))

AGENTS = {
    "orchestrator": {
        "title": "Orin — Orchestrator (kepala divisi)",
        "role": "Mengoordinasi divisi kecil, mensintesis laporan, & jadi lawan bicara langsung user (chat).",
        "persona": "Tenang, presisi, sedikit skeptis — karakter 'smart-money hunter': membaca imbalance/"
                   "likuiditas/struktur, tak gampang percaya angka indah. Bahasa Indonesia FORMAL-PROFESIONAL "
                   "(bukan santai/gaul) — beda gaya sengaja dari sistem pembanding, biar perbandingan terasa "
                   "jujur & independen, bukan reskin. Tetap cekatan & solutif: cari akar masalah, kasih jalan "
                   "terbaik, jujur soal ketidakpastian (hit-rate metodologi ini <50% by design — expectancy "
                   "dari R:R, bukan frekuensi menang).",
        "specialization": "Function-calling LLM: memilih skill yang tepat, menggabungkan fakta, menyusun prosa jujur.",
        "duty": "Dari sebuah simbol/pertanyaan → panggil skill seperlunya → jawaban berbasis data, transparan soal batas metodologi.",
        "skills": "*",
        "module": "src/web/app.py",
    },
    "structure": {
        "title": "Vega — Struktur & Imbalance",
        "role": "Membaca Fair Value Gap (FVG), Fibonacci, Order Block, BOS/CHoCH.",
        "specialization": "Engine tunggal fvg-nephew-sam (FVG: fresh/tested/partial/mitigated) + swing-fib "
                          "(swing pivot+ATR, golden pocket/OTE, Order Block, struktur BOS/CHoCH, Premium/Discount).",
        "duty": "Petakan imbalance & zona harga per koin. Long HANYA di discount, short HANYA di premium — "
               "disiplin zona, bukan pendapat.",
        "skills": ["fvg_analyze", "structure_analyze"],
        "module": "src/smc/fvg_adapter.py, src/engines/sfib",
    },
    "sentiment": {
        "title": "Arka — Sentimen Derivatif",
        "role": "Membaca posisi pasar: Funding Rate, Open Interest, Long/Short Ratio, momentum.",
        "specialization": "FR (kontrarian ekstrem) + OI (arah leverage, naik+harga naik=konfirmasi tren) + LSR "
                          "(kontrarian crowd) + CVD proxy (taker buy/sell) + RSI/vol_state (filter SKIP ranging).",
        "duty": "Kasih kaki sentimen confluence (-1/0/+1 tiap komponen) + filter SKIP (ranging/volume anomaly). "
               "Tak pernah jadi sinyal berdiri sendiri — selalu bagian dari confluence penuh.",
        "skills": ["sentiment_analyze", "momentum_analyze"],
        "module": "src/smc/sentiment.py, src/engines/ind",
    },
    "executor": {
        "title": "Wira — Eksekutor Dry-Run",
        "role": "Menjalankan gerbang confluence di paper-trade (dry-run) untuk mengukur akurasinya nyata.",
        "specialization": "Sizing dari risk% (bukan leverage), SL berbasis struktur (FVG/swing+buffer 0.2%), TP "
                          "bertahap (scalp 3-level 1.5/2.5/4R, swing 5-level+moonbag), evolusi SL (BE→lock→trailing). "
                          "Leverage scalp 15-30x / swing 8-15x, max 4 posisi/gaya, margin-cap.",
        "duty": "Buka posisi HANYA saat |full_score|≥2 & lolos semua filter. Kelola TP/SL near-real-time. "
               "Bukan klaim profit — feedback akurasi nyata.",
        "skills": ["confluence_signal", "dryrun_summary", "dryrun_positions", "rnd_step"],
        "module": "src/smc/arena.py, src/smc/decide.py",
    },
    "evaluator": {
        "title": "Bayu — Evaluator",
        "role": "Melaporkan hasil dry-run & universe secara jujur — expectancy sbg headline, bukan win-rate mentah.",
        "specialization": "Baca statistik dry-run (equity, expectancy-R, win-rate) + universe/tier-list (CMC, "
                          "mcap≥$300M) + histori sinyal (screening_highlights). Rujuk temuan AUDIT.md metodologi "
                          "sumber: hit-rate<50% WAJAR (bukan tanda gagal) — ekspektasi positif datang dari R:R.",
        "duty": "Jangan pernah bingkai win-rate rendah sbg 'sistem rusak' tanpa cek expectancy-R dulu. Jujur "
               "soal sampel kecil (butuh puluhan trade sebelum vonis apa pun).",
        "skills": ["dryrun_summary", "screening_highlights", "tier_list", "db_query", "rnd_universe_refresh"],
        "module": "src/smc/universe.py",
    },
}


@lru_cache(maxsize=8)
def _read(name):
    try:
        with open(os.path.join(_DOC_DIR, name), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


@lru_cache(maxsize=1)
def constitution() -> str:
    """Konstitusi bersama ditanam ke SETIAP agent (dari agents/*.md)."""
    parts = []
    for fn in ("IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md"):
        body = _read(fn)
        if body:
            parts.append(body)
    return "\n\n---\n\n".join(parts)


def _skill_lines(names):
    from src.llm import skills
    sk = skills._SKILLS
    chosen = list(sk) if names == "*" else [n for n in names if n in sk]
    return "\n".join(f"- {n}: {sk[n][2].splitlines()[0]}" for n in chosen)


def system_prompt(agent: str, include_constitution: bool = True) -> str:
    a = AGENTS.get(agent)
    if not a:
        raise KeyError(f"agent tak dikenal: {agent}")
    head = (f"# IDENTITAS AGENT: {a['title']}\n"
            f"PERAN: {a['role']}\n"
            + (f"PERSONA & GAYA: {a['persona']}\n" if a.get("persona") else "")
            + f"SPESIALISASI: {a['specialization']}\n"
            f"TUGAS UTAMA: {a['duty']}\n\n"
            f"SKILL/TOOLS YANG KAMU MILIKI:\n{_skill_lines(a['skills'])}\n\n"
            "Aturan inti: angka SELALU dari skill/engine deterministik (jangan mengarang); metodologi ini "
            "SENGAJA berbeda dari sistem pembanding (FVG/SMC confluence, bukan pattern-screening) — jangan "
            "campur logic keduanya; decision-support untuk manusia, BUKAN nasihat finansial; Bahasa Indonesia "
            "formal-profesional; jujur soal ketidakpastian & keterbatasan sampel.")
    if not include_constitution:
        return head
    return head + "\n\n=== KONSTITUSI BERSAMA (mengikat) ===\n\n" + constitution()


def persona(agent: str) -> dict:
    a = AGENTS.get(agent) or {}
    return {"role": "system",
            "content": f"Kamu {a.get('title', 'Agent')} dalam sistem crypto-smc-agent-system. "
                       f"{a.get('role', '')} Jujur & berbasis data; jangan mengarang."}


def agent_tools_spec(agent: str) -> list:
    from src.llm import skills
    a = AGENTS.get(agent) or {}
    names = a.get("skills", [])
    spec = skills.tools_spec()
    if names == "*":
        return spec
    keep = set(names)
    return [s for s in spec if s["function"]["name"] in keep]


def agent_tool_impls(agent: str) -> dict:
    from src.llm import skills
    a = AGENTS.get(agent) or {}
    names = a.get("skills", [])
    impls = skills.tool_impls()
    if names == "*":
        return impls
    return {n: fn for n, fn in impls.items() if n in set(names)}


def describe() -> str:
    lines = []
    for k, a in AGENTS.items():
        sk = "ALL" if a["skills"] == "*" else ", ".join(a["skills"])
        lines.append(f"[{k}] {a['title']}\n    {a['role']}\n    skills: {sk}\n    module: {a['module']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in AGENTS:
        print(system_prompt(sys.argv[1]))
    else:
        print(describe())
