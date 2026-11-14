import base64
import json
import re
import os
import sys
import time
import subprocess
import hashlib
import hmac
import ipaddress
import threading
import requests
import pandas as pd
import altair as alt
import streamlit as st
import streamlit.components.v1 as components

# 1. Page Configuration
st.set_page_config(
    page_title="Alexander J Miller",
    page_icon="💾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Navigation Cards
st.markdown(
    """
    <style>
    .nav-card {
        background-color: #f8f9fa;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        margin-bottom: 10px;
    }
    .nav-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        border-color: #cbd5e1;
    }
    .nav-card a {
        text-decoration: none;
        color: #0f172a;
        font-weight: 600;
        font-size: 1.05rem;
        display: block;
    }
    .nav-sub {
        font-size: 0.85rem;
        color: #64748b;
        margin-top: 4px;
    }
    /* Top tabs: larger, with big emoji, and closer to the top */
    .block-container { padding-top: 2rem !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 14px; }
    .stTabs [data-baseweb="tab"] { height: 3.6rem; padding: 0 24px; }
    .stTabs [data-baseweb="tab"] p,
    .stTabs [data-baseweb="tab"] div[data-testid="stMarkdownContainer"] p {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
    /* AI Chat: make the input obvious */
    [data-testid="stChatInput"] {
        border: 2px solid #2563eb !important;
        border-radius: 16px !important;
        box-shadow: 0 0 0 4px rgba(37,99,235,0.18), 0 6px 20px rgba(37,99,235,0.15) !important;
    }
    [data-testid="stChatInput"] textarea { font-size: 1.15rem !important; }
    [data-testid="stChatInput"]:focus-within {
        box-shadow: 0 0 0 5px rgba(37,99,235,0.35), 0 6px 24px rgba(37,99,235,0.25) !important;
    }
    /* AI Chat stats row: compact, with space before the chat window */
    .st-key-chatstats { margin-bottom: 1.25rem; }
    .st-key-chatstats [data-testid="stMetricValue"] { font-size: 1.35rem !important; }
    .st-key-chatstats [data-testid="stMetricLabel"] p { font-size: 0.8rem !important; }
    /* No fullscreen button on images */
    [data-testid="stImage"] [data-testid="stElementToolbar"],
    button[title="View fullscreen"] { display: none !important; }
    /* AI Chat: model line + tight stats row */
    .st-key-chatmodel { position: relative; z-index: 2; }
    .st-key-chatmodel p { font-size: 1.3rem !important; margin: 0 !important; }
    .st-key-chatmodel code { font-size: 1.1rem !important; }
    .st-key-chatstats { margin-top: -3rem; }
    /* Sidebar social links: same icon size, same left edge, soft white text in dark mode */
    .side-link {
        display: flex; align-items: center; gap: 0.6rem;
        margin: 0 0 0.5rem 0; padding: 0;
        text-decoration: none !important;
        font-size: 1.25rem; font-weight: 300;
        color: #31333F !important;
    }
    .side-link span { color: inherit !important; }
    .side-icon { height: 2rem; width: 2rem; flex: none; display: block; }
    @media (prefers-color-scheme: dark) { .side-link { color: #E3E5E8 !important; } }
    /* Chat sidebar options: tabs switch client-side, so show them with :has() instead of a rerun */
    .st-key-chatopts { display: none; }
    .st-key-chatopts [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    .st-key-chatopts [data-testid="stMetricLabel"] p { font-size: 0.85rem !important; }
    .stApp:has([data-baseweb="tab-list"] button[aria-selected="true"]:nth-of-type(2)) .st-key-chatopts { display: block; }
    </style>
""",
    unsafe_allow_html=True,
)

#---------------------------------------------------------



# ---- Tabs (client-side switching; sidebar stays put) ----
tab_dash, tab_chat, tab_synthea = st.tabs(["📊 Dashboard", "💬 AI Chat", "🩺 What is Synthea"])

with tab_synthea:
    st.title("What is Synthea?")
    st.write(
        "**Synthea™** is an open-source synthetic patient generator, created by "
        "[MITRE](https://www.mitre.org/), that produces realistic — but entirely "
        "fictional — healthcare records."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Why it exists")
        st.markdown(
            "- Real patient data is locked behind privacy rules (HIPAA), making it hard to share, demo, or test against.\n"
            "- Synthea creates people who never existed, so there is **no privacy risk** and no consent hurdles.\n"
            "- The data is realistic enough for analytics, software testing, education, and research."
        )
        st.markdown("### What it generates")
        st.markdown(
            "- Full life histories, from birth to death\n"
            "- Encounters, conditions, medications, procedures, immunizations, and lab observations\n"
            "- Care plans, allergies, imaging studies, and insurance claims\n"
            "- Output as **FHIR (JSON)**, C-CDA, CSV"
        )
    with c2:
        st.markdown("### How it works")
        st.markdown(
            "- Each patient is simulated year by year using **disease-progression modules**: state machines "
            "modeled on published clinical guidelines and statistics.\n"
            "- Demographics follow US Census data, and disease prevalence follows public health statistics.\n"
            "- Modules are open and extensible, covering conditions like diabetes, asthma, cancer, and heart disease."
        )
        st.markdown("### Its role in this project")
        st.markdown(
            "Synthea is step one of the pipeline: it generates patient JSON, which is loaded into "
            "PostgreSQL, transformed by dbt, and pushed to Snowflake. The **Dashboard** tab shows "
            "how much data has flowed through so far."
        )
    st.divider()
    st.markdown(
        "🔗 [Synthea Website](https://synthetichealth.github.io/synthea/) · [Synthea on GitHub](https://github.com/synthetichealth/synthea) · "
        "[Project wiki](https://github.com/synthetichealth/synthea/wiki)"
    )


# =====================================================================================
# AI CHAT TAB: public chat with the home-hosted Qwen model (vLLM, OpenAI-compatible API)
# Fairness: ONE reply at a time per visitor (by IP), a few messages/min per visitor.
# vLLM queues requests across visitors, so the UI shows a waiting indicator + live load.
# Thinking is ON; reasoning streams into a collapsible box. No database/web access (yet).
# =====================================================================================


def _model_host():
    """Address of the model server, read from the git-ignored file .model_host (default: localhost)."""
    try:
        with open(os.path.join(os.path.dirname(__file__), ".model_host")) as f:
            return f.read().strip() or "127.0.0.1"
    except OSError:
        return "127.0.0.1"


MODEL_HOST = _model_host()
QWEN_URL = f"http://{MODEL_HOST}:8000/v1/chat/completions"
QWEN_METRICS_URL = f"http://{MODEL_HOST}:8000/metrics"
GPU_STATS_URL = f"http://{MODEL_HOST}:9100/gpu"
QWEN_MODELS_URL = f"http://{MODEL_HOST}:8000/v1/models"
QWEN_MODEL = "Qwen3.8-27B"
GPU_COUNT, GPU_GB = 2, 24  # dual RTX 3090
# Claude API list prices, USD per 1M tokens (input, output), from the API reference cached 2026-11-03
CLOUD_PRICES = {
    "Claude Haiku 5.5": (0.10, 0.50),
    "Claude Sonnet 5.5": (2.00, 10.00),
    "Claude Opus 5.5": (4.00, 20.00),
    "Claude Fable 5.2": (8.00, 40.00),
}
CHAT_MAX_MSGS_PER_MIN = 10      # per visitor IP
CHAT_MAX_INPUT_CHARS = 4000
CHAT_MAX_HISTORY = 20           # most recent messages sent to the model
CHAT_MAX_SECONDS = 600          # safety net only (10 min per reply)
CHAT_ACTIVE_WINDOW = 600        # a visitor counts as "recent" for 10 minutes
CHAT_SYSTEM_PROMPT = (
    "You are the AI assistant on a portfolio website that showcases a synthetic-healthcare data "
    "engineering pipeline. You run as Qwen3.8-27B (4-bit AWQ, served by vLLM) on a private home server with two NVIDIA RTX 3090 GPUs, not in the cloud. About the project: "
    "Synthea generates synthetic patient data (FHIR JSON); it is loaded into PostgreSQL; dbt "
    "transforms it into structured tables; the tables are pushed to Snowflake; Airflow orchestrates "
    "the workflow, Marquez tracks data lineage, Metabase is used to explore the data, and this "
    "dashboard is built with Streamlit. All patient data is synthetic: no real people and no real "
    "PHI. You do NOT have access to the database, live metrics, or the internet, so never claim to "
    "look anything up or invent figures; for live numbers, point to the Dashboard tab. Be friendly, "
    "concise and accurate. Do not give medical advice. If you do not know, say so."
)


@st.cache_resource
def _chat_registry():
    """Process-wide state shared by every visitor session (in memory only, never persisted)."""
    return {"lock": threading.Lock(), "busy": {}, "times": {}, "seen": {}}


@st.cache_data(ttl=5)
def _model_stats():
    """Context window, KV-cache fill and lifetime token counters from vLLM, or None if unreachable."""
    try:
        text = requests.get(QWEN_METRICS_URL, timeout=2).text
        info = requests.get(QWEN_MODELS_URL, timeout=2).json()["data"][0]
    except Exception:
        return None
    wanted = {
        "kv": "vllm:kv_cache_usage_perc{",
        "ptot": "vllm:prompt_tokens_total{",
        "gtot": "vllm:generation_tokens_total{",
        "since": "vllm:prompt_tokens_created{",
    }
    v = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        for key, prefix in wanted.items():
            if line.startswith(prefix):
                v[key] = float(line.rsplit(" ", 1)[1])
    return {
        "ctx": info.get("max_model_len"),
        "kv": v.get("kv"),
        "root": info.get("root"),
        "prompt_total": v.get("ptot", 0.0),
        "gen_total": v.get("gtot", 0.0),
        "served": v.get("ptot", 0.0) + v.get("gtot", 0.0),
        "since": v.get("since"),
    }


@st.cache_data(ttl=3)
def _gpu_stats():
    """Per-card VRAM from the nvidia-smi endpoint on the model VM, or None."""
    try:
        return requests.get(GPU_STATS_URL, timeout=2).json()["gpus"]
    except Exception:
        return None


def _vram_html(gpus):
    """Two stacked bars: GB used vs total for each card."""
    parts = ['<div style="font-size:0.875rem;opacity:0.7">🎮 GPU VRAM</div>']
    for g in gpus:
        used, total = g["used_mib"] / 1024, g["total_mib"] / 1024
        pct = 100 * used / total if total else 0
        parts.append(
            f'<div style="display:flex;justify-content:space-between;font-size:0.9rem;margin-top:6px">'
            f'<span>GPU {g["index"] + 1}</span><span><b>{used:.1f}</b> / {total:.1f} GB</span></div>'
            f'<div style="height:9px;border-radius:5px;background:rgba(128,128,128,0.25);overflow:hidden">'
            f'<div style="width:{pct:.0f}%;height:100%;background:#2563eb"></div></div>'
        )
    return '<div style="padding-bottom:24px">' + "".join(parts) + "</div>"  # lift so the bars line up with the other values


def _show_ctx(slot, ctx_max):
    """Tokens in this visitor's conversation (prompt + latest reply) out of the model's window."""
    used = st.session_state.get("ctx_used", 0)
    if ctx_max:
        slot.metric(
            "📏 Context Window (tokens)",
            f"{used:,} / {ctx_max // 1024}K ({used / ctx_max * 100:.1f}%)",
            help=f"Tokens your conversation occupies out of the model's {ctx_max:,}-token window "
                 "(system prompt + chat history + the latest reply). A fixed ceiling per chat.",
        )
    else:
        slot.metric("📏 Context Window (tokens)", "n/a")


TOKENS_FILE = ".tokens_served.json"  # tokens served through THIS site only (not the shared model server)


@st.cache_resource
def _tokens_lock():
    return threading.Lock()


def _read_tokens():
    try:
        with open(TOKENS_FILE, "r") as f:
            d = json.load(f)
    except Exception:
        d = {}
    return {
        "prompt": int(d.get("prompt", 0)), "gen": int(d.get("gen", 0)),
        "replies": int(d.get("replies", 0)), "since": d.get("since") or time.time(),
    }


def _add_tokens(prompt, gen):
    with _tokens_lock():
        d = _read_tokens()
        d["prompt"] += int(prompt)
        d["gen"] += int(gen)
        d["replies"] += 1
        tmp = TOKENS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, TOKENS_FILE)


def _show_served(slot):
    """All-time tokens served through this site (replaces the old speed tile)."""
    life = _read_tokens()
    tier = st.session_state.get("cloud_tier", "Claude Sonnet 5.5")
    rin, rout = CLOUD_PRICES.get(tier, CLOUD_PRICES["Claude Sonnet 5.5"])
    cost = (life["prompt"] * rin + life["gen"] * rout) / 1e6
    since = time.strftime("%b %d", time.localtime(life["since"]))
    slot.metric(
        "🪙 All Time Tokens (In/Out)", f'{_compact(life["prompt"])} / {_compact(life["gen"])}',
        help=f"Tokens in / tokens out (prompt / generated) handled by this site's chat since {since}, across all visitors "
             f"({life['replies']:,} replies). Roughly {_fmt_usd(cost)} on {tier}; no per-token fees here.",
    )


def _compact(n):
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            return f"{n / div:.2f}{suffix}" if n < 10 * div else f"{n / div:.1f}{suffix}"
    return f"{int(n)}"


def _fmt_usd(x):
    return f"${x:,.4f}" if x < 1 else f"${x:,.2f}"


def _show_last_stats(slot):
    """One stat line for the visitor's most recent reply (sits under the chat window)."""
    ls = st.session_state.get("last_stats")
    if not ls:
        slot.caption("&nbsp;")  # same height as a filled line: nothing shifts when the first reply lands
        return
    parts = [
        f"{ls['tokens']:,} tokens",
        f"{ls['speed']:.0f} tok/s",
        f"{ls['ttft']:.1f}s to first token",
        f"thought {ls['thought']:.1f}s" if ls["thinking"] else "thinking off",
        f"{ls['total']:.1f}s total",
    ]
    slot.caption("🧾 Last reply: " + " · ".join(parts))


def _normalize_ip(ip):
    """IPv4 as-is; IPv6 grouped by its /64 (one household can own billions of addresses)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(ip + "/64", strict=False))
    return ip


def _client_id():
    """Visitor IP as set by nginx (X-Real-IP is overwritten by nginx, so it cannot be spoofed)."""
    try:
        headers = st.context.headers
        ip = (headers.get("X-Real-Ip") or "").strip()
        if not ip:
            ip = (headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
    except Exception:
        ip = ""
    if ip:
        return _normalize_ip(ip)
    if "chat_sid" not in st.session_state:
        st.session_state.chat_sid = "session-" + os.urandom(6).hex()
    return st.session_state.chat_sid


def _qwen_stream(messages, opts=None):
    """Yield ("reasoning", text) then ("answer", text) pieces from the model."""
    opts = opts or {}
    payload = {
        "model": QWEN_MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": opts.get("temperature", 0.6),
        "top_p": opts.get("top_p", 0.95),
        "chat_template_kwargs": opts.get("template_kwargs", {"reasoning_effort": "low"}),
    }
    deadline = time.time() + CHAT_MAX_SECONDS
    with requests.post(QWEN_URL, json=payload, stream=True, timeout=(5, CHAT_MAX_SECONDS)) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        for line in resp.iter_lines(decode_unicode=True):
            if time.time() > deadline:
                yield ("answer", " (reply stopped: time limit reached)")
                return
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                return
            obj = json.loads(data)
            usage = obj.get("usage") or {}
            if usage.get("prompt_tokens"):
                yield ("prompt_usage", usage["prompt_tokens"])
            if usage.get("completion_tokens"):
                yield ("usage", usage["completion_tokens"])
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            thought = delta.get("reasoning") or delta.get("reasoning_content")
            if thought:
                yield ("reasoning", thought)
            piece = delta.get("content")
            if piece:
                yield ("answer", piece)


# Thinking effort as the model server understands it (it accepts low / medium / xhigh, or thinking off)
EFFORT_KWARGS = {
    "Off": {"enable_thinking": False},
    "Low": {"reasoning_effort": "low"},
    "Medium": {"reasoning_effort": "medium"},
    "Max": {"reasoning_effort": "xhigh"},
}
CHAT_DEFAULTS = {"chat_effort": "Low", "chat_temp": 0.6, "chat_top_p": 0.95}


def _chat_opts():
    """This visitor's sidebar settings (widget values reach session_state before the script reruns)."""
    ss = st.session_state
    return {
        "temperature": ss.get("chat_temp", CHAT_DEFAULTS["chat_temp"]),
        "top_p": ss.get("chat_top_p", CHAT_DEFAULTS["chat_top_p"]),
        "template_kwargs": EFFORT_KWARGS.get(ss.get("chat_effort", "Low"), EFFORT_KWARGS["Low"]),
    }


def _reset_chat_opts():
    for k, v in CHAT_DEFAULTS.items():
        st.session_state[k] = v
    st.session_state.pop("system_prompt", None)


@st.dialog("📝 System prompt", width="large")
def _system_prompt_dialog():
    st.caption("The instructions the model follows for every reply. Changes apply to your session only.")
    txt = st.text_area(
        "System prompt",
        value=st.session_state.get("system_prompt", CHAT_SYSTEM_PROMPT),
        height=280,
        max_chars=2000,
        label_visibility="collapsed",
    )
    c1, c2 = st.columns(2)
    if c1.button("Save", type="primary", width="stretch"):
        st.session_state.system_prompt = txt.strip() or CHAT_SYSTEM_PROMPT
        st.rerun()
    if c2.button("Reset to default", width="stretch"):
        st.session_state.pop("system_prompt", None)
        st.rerun()


@st.cache_data
def _hero_html(path, mtime):
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext, "png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (
        '<div style="height:460px;display:flex;align-items:center;justify-content:center;">'
        f'<img src="data:image/{mime};base64,{b64}" '
        'style="width:22%;max-width:260px;min-width:140px;pointer-events:none;user-select:none;" alt=""></div>'
    )


with tab_chat:
    st.title("Chat with a self-hosted AI")
    _ms0 = _model_stats()
    _root = _ms0.get("root") if _ms0 else None
    st.container(key="chatmodel").markdown(
        f"**Model:** [`{QWEN_MODEL}`](https://huggingface.co/Qwen/{QWEN_MODEL})"
        + (f" · [`{_root}`](https://huggingface.co/{_root})" if _root else "")
    )

    reg = _chat_registry()
    cid = _client_id()

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    admin = False  # no admin bypass: every visitor shares the same limits

    # --- live stats ---
    snap_now = time.time()
    with reg["lock"]:
        reg["seen"][cid] = snap_now  # presence: loading or using the page counts
        for k in [k for k, v in reg["seen"].items() if snap_now - v > CHAT_ACTIVE_WINDOW]:
            del reg["seen"][k]
        recent_visitors = len(reg["seen"])
    ms = _model_stats()
    gpus = _gpu_stats()
    c1, c2, c3, c4, _gap, c5 = st.container(key="chatstats").columns([1, 1.65, 1.85, 1.6, 0.15, 1.1], vertical_alignment="bottom")
    c1.metric("👥 Active users", recent_visitors,
              help=f"Visitors who chatted in the last {CHAT_ACTIVE_WINDOW // 60} minutes")
    ctx_slot = c2.empty()
    _show_ctx(ctx_slot, ms["ctx"] if ms else None)
    tokens_slot = c3.empty()
    _show_served(tokens_slot)
    if gpus:
        c4.markdown(_vram_html(gpus), unsafe_allow_html=True)
    else:
        c4.metric("🎮 GPU VRAM", "n/a")
    c5.metric("🧠 KV cache in use", f"{ms['kv'] * 100:.0f}%" if ms and ms["kv"] is not None else "n/a",
              help="A live fill level, not a limit: how much of the GPU memory pool that holds every active "
                   "conversation's working state is in use right now, across all visitors at once.")

    # Framed, scrollable chat window; the input sits right below it
    chat_box = st.container(height=520, border=True)
    hero_slot = chat_box.empty()
    if not st.session_state.chat_messages:
        _hero = next((f for f in ("chat_hero.png", "chat_hero.jpg", "chat_hero.jpeg", "chat_hero.webp", "chat_hero.gif")
                      if os.path.exists(f)), None)
        if _hero:
            hero_slot.markdown(_hero_html(_hero, os.path.getmtime(_hero)), unsafe_allow_html=True)
    for m in st.session_state.chat_messages:
        with chat_box.chat_message(m["role"]):
            if m.get("reasoning"):
                with st.expander("🧠 Reasoning", expanded=False):
                    st.markdown(m["reasoning"])
            st.markdown(m["content"])

    stat_slot = st.empty()
    _show_last_stats(stat_slot)

    prompt = st.chat_input("Chat here...", max_chars=CHAT_MAX_INPUT_CHARS)

    if prompt:
        hero_slot.empty()  # image disappears the moment a message is sent
        now_ts = time.time()
        verdict = None
        busy_key = cid if not admin else cid + "#" + os.urandom(3).hex()
        with reg["lock"]:
            for k in [k for k, v in reg["busy"].items() if now_ts - v > CHAT_MAX_SECONDS + 60]:
                del reg["busy"][k]  # stale entry safety net
            recent = [t for t in reg["times"].get(cid, []) if now_ts - t < 60]
            if not admin:
                if cid in reg["busy"]:
                    verdict = ("busy", 0)
                elif len(recent) >= CHAT_MAX_MSGS_PER_MIN:
                    verdict = ("rate", int(60 - (now_ts - recent[0])) + 1)
            if verdict is None:
                recent.append(now_ts)
                reg["times"][cid] = recent
                reg["seen"][cid] = now_ts
                reg["busy"][busy_key] = now_ts

        if verdict and verdict[0] == "busy":
            st.info("You already have a reply in progress. Please wait for it to finish.")
        elif verdict and verdict[0] == "rate":
            st.warning(f"Easy there: {CHAT_MAX_MSGS_PER_MIN} messages per minute max. Try again in about {verdict[1]}s.")
        else:
            try:
                st.session_state.chat_messages.append({"role": "user", "content": prompt})
                with chat_box.chat_message("user"):
                    st.markdown(prompt)

                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_messages[-CHAT_MAX_HISTORY:]
                ]
                messages = [{"role": "system", "content": st.session_state.get("system_prompt") or CHAT_SYSTEM_PROMPT}] + history

                with chat_box.chat_message("assistant"):
                    status = st.status("⏳ Waiting for the model...", expanded=False)
                    think_box = status.empty()
                    answer_box = st.empty()
                    reasoning, answer = "", ""
                    started = time.time()
                    first_tok, n_chunks, usage_tokens, prompt_tokens, ans_t = None, 0, None, None, None
                    last_paint = 0.0
                    thinking_shown = False
                    try:
                        for kind, piece in _qwen_stream(messages, _chat_opts()):
                            if kind == "usage":
                                usage_tokens = piece
                                continue
                            if kind == "prompt_usage":
                                prompt_tokens = piece
                                continue
                            if first_tok is None:
                                first_tok = time.time()
                            n_chunks += 1
                            if kind == "reasoning":
                                if not thinking_shown:
                                    status.update(label="🧠 Thinking...")
                                    thinking_shown = True
                                reasoning += piece
                                if time.time() - last_paint > 0.2:
                                    think_box.markdown(reasoning)
                                    last_paint = time.time()
                            else:
                                if not answer:
                                    think_box.markdown(reasoning)
                                    ans_t = time.time()
                                    secs = int(ans_t - started)
                                    status.update(label=(f"🧠 Thought for {secs}s" if thinking_shown else "💬 Replying"), state="complete", expanded=False)
                                answer += piece
                                if time.time() - last_paint > 0.05:
                                    answer_box.markdown(answer + " ▌")
                                    last_paint = time.time()
                        answer_box.markdown(answer)
                        gen_secs = time.time() - first_tok if first_tok else 0
                        toks = usage_tokens or n_chunks
                        if gen_secs > 0.2 and toks:
                            st.session_state.last_speed = toks / gen_secs
                            st.session_state.last_stats = {
                                "tokens": toks, "speed": toks / gen_secs, "ttft": first_tok - started,
                                "thought": (ans_t - first_tok) if (thinking_shown and ans_t) else 0,
                                "total": time.time() - started, "thinking": thinking_shown,
                            }
                            _show_last_stats(stat_slot)
                        if prompt_tokens and usage_tokens:
                            st.session_state.ctx_used = prompt_tokens + usage_tokens
                            _show_ctx(ctx_slot, ms["ctx"] if ms else None)
                            st.session_state.cloud_in = st.session_state.get("cloud_in", 0) + prompt_tokens
                            st.session_state.cloud_out = st.session_state.get("cloud_out", 0) + usage_tokens
                            _add_tokens(prompt_tokens, usage_tokens)
                            _show_served(tokens_slot)
                        if not answer:
                            raise ValueError("empty answer")
                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": answer, "reasoning": reasoning}
                        )
                    except Exception:
                        st.session_state.chat_messages.pop()  # drop the unanswered user message
                        status.update(label="⚠️ No reply", state="error", expanded=False)
                        st.error("The model didn't return an answer (it may be unreachable or hit its limit). Please try again.")
            finally:
                with reg["lock"]:
                    reg["busy"].pop(busy_key, None)

    if st.session_state.chat_messages and st.button("🧹 Clear chat"):
        st.session_state.chat_messages = []
        st.session_state.ctx_used = 0
        for _k in ("last_stats", "cloud_in", "cloud_out"):
            st.session_state.pop(_k, None)
        st.rerun()

with tab_dash:

    st.title("Synthea ELT Pipeline")
    st.write("") # Spacing

    # Create 4 columns for the 4 steps
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("### 💻 **Synthea**")
        st.info("Synthea generates synthetic healthcare data as JSON files")

    with col2:
        st.markdown("### 🗄️  **PostgreSQL**")
        st.info("Raw JSON is loaded into a PostgreSQL database")

    with col3:
        st.markdown("### 🔄 **dbt Transformation**")
        st.info("dbt is used to convert raw JSON into structured tables")

    with col4:
        st.markdown("### ❄️  **Snowflake**")
        st.info("Flattened tables are pushed to Snowflake for long-term storage")

    st.divider()
    #----------------------------------------------------------

    # 2. Strict Data Loader
    @st.cache_data(ttl=60)
    def load_cached_metrics(cache_mtime):
        json_path = "snowflake_cache.json"

        if not os.path.exists(json_path):
            raise FileNotFoundError(
                "snowflake_cache.json not found. Run 'python query_snowflake.py' to fetch data."
            )

        with open(json_path, "r") as f:
            cache_payload = json.load(f)

        metrics = cache_payload.get("metrics", {})
        trend = pd.DataFrame(cache_payload.get("trend", []))

        if not metrics:
            raise ValueError("snowflake_cache.json contains empty metrics.")

        return metrics, trend


    # LinkedIn link (above GitHub in the sidebar)
    _LI_PATH = "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
    # GitHub link (top of sidebar)
    _GH_ICON = "data:image/png;base64,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"
    st.sidebar.markdown(
        f'<a class="side-link" href="https://www.linkedin.com/in/ajmiller2357/" target="_blank">'
        f'<svg viewBox="0 0 24 24" class="side-icon" aria-hidden="true"><rect x="3" y="3" width="18" height="18" fill="#FFFFFF"/><path fill="#0A66C2" d="{_LI_PATH}"/></svg>'
        f'<span>in/ajmiller2357</span></a>'
        f'<a class="side-link" href="https://github.com/MillerAJ" target="_blank">'
        f'<img class="side-icon" src="{_GH_ICON}" style="border-radius:50%;"><span>github.com/MillerAJ</span></a>',
        unsafe_allow_html=True,
    )


    @st.cache_data(ttl=60)
    def load_hourly(cache_mtime):
        """Hourly patients-added / rows-added series from the same cache file."""
        try:
            with open("snowflake_cache.json", "r") as f:
                return pd.DataFrame(json.load(f).get("trend_hourly", []))
        except Exception:
            return pd.DataFrame()

    # Sidebar Status check  -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   Sidebar
    _status = None
    cache_path = "snowflake_cache.json"
    if os.path.exists(cache_path):
        mod_time = os.path.getmtime(cache_path)
        ts = pd.to_datetime(mod_time, unit="s", utc=True).tz_convert("America/New_York")
        sync_time = ts.strftime("%Y-%m-%d %I:%M:%S %p ") + ts.tzname()  # e.g. 2026-11-14 12:17:04 AM EST
        _status = ("success", f"Last updated: `{sync_time}`")
        cache_mtime = mod_time
    else:
        _status = ("error", "No data loaded: `snowflake_cache.json` is missing.")
        cache_mtime = 0

    try:
        metrics, df_trend = load_cached_metrics(cache_mtime)
    except Exception as e:
        st.error(f"Failed to load metrics: {e}")
        st.stop()

    # Define cooldown duration (30 minutes in seconds)
    COOLDOWN_SECONDS = 5 * 60
    LOCK_FILE = ".refresh_lock"

    # Initialize last_refresh timestamp in session_state if not present
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = 0

    now = time.time()
    elapsed = now - st.session_state.last_refresh
    time_remaining = COOLDOWN_SECONDS - elapsed


    # --- PERSISTENT DATA REFRESH LOGIC ---
    st.sidebar.header("⚙️ Data Refresh")

    COOLDOWN_SECONDS = .15 * 60  # 5 minutes
    LOCK_FILE = os.path.join(os.path.dirname(__file__), ".refresh_lock")


    def get_last_refresh_time():
        """Reads the last refresh timestamp from disk."""
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "r") as f:
                    content = f.read().strip()
                    return float(content) if content else 0.0
            except Exception as e:
                st.sidebar.warning(f"Could not read lock file: {e}")
                return 0.0
        return 0.0


    def set_last_refresh_time():
        """Writes the current epoch timestamp to disk."""
        try:
            with open(LOCK_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception as e:
            st.sidebar.error(f"Failed to write lock file: {e}")


    # Read lock timestamp directly from disk
    last_refresh = get_last_refresh_time()
    now = time.time()
    elapsed = now - last_refresh
    time_remaining = COOLDOWN_SECONDS - elapsed


    if time_remaining > 0 and last_refresh > 0:
        # Calculate minutes left (rounding up)
        minutes_left = int((time_remaining + 59) // 60)
        min_str = "minute" if minutes_left == 1 else "minutes"
                                                                    
        # Lock button state
        st.sidebar.button(
            f"⏳ Please wait {minutes_left} {min_str}...",
            disabled=True,
            use_container_width=True,
            help=f"Cache refresh locked until 5-minute cooldown expires.",
        )
    else:
        # Active Refresh Button
        if st.sidebar.button(
            "🔄 Refresh Database Totals",
            use_container_width=True,
            help="Click to re-run Snowflake queries.",
        ):
            with st.spinner("⏳ Querying Snowflake database... Please wait..."):
                # 1. WRITE LOCK IMMEDIATELY to prevent double clicks/bypasses
                set_last_refresh_time()

                try:
                    # 2. Run background script
                    result = subprocess.run(
                        [sys.executable, "query_snowflake.py"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    # 3. Invalidate cache & reload app
                    st.cache_data.clear()
                    st.sidebar.success("✅ Cache updated successfully!")
                    time.sleep(1)
                    st.rerun()

                except subprocess.CalledProcessError as err:
                    st.sidebar.error(f"❌ Refresh failed: {err.stderr}")

    # Status box now sits below the refresh button
    if _status:
        (st.sidebar.success if _status[0] == "success" else st.sidebar.error)(_status[1])

    # Display cache file timestamp
    # cache_path = "snowflake_cache.json"
    # if os.path.exists(cache_path):
    #     mod_time = os.path.getmtime(cache_path)
    #     sync_time = pd.to_datetime(mod_time, unit="s").strftime("%Y-%m-%d %H:%M:%S")
        # st.sidebar.caption(f"Last updated: `{sync_time}`")




    # ---   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -   -    QUICK ACCESS
    st.subheader("🔗 Pipeline Links")
    col_nav1, col_nav2, col_nav3 = st.columns(3)

    with col_nav1:
        metabase_card_html = """
        <style>
            .mb-btn {
                width: 100%;
                background-color: #f8f9fa;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
                text-align: center;
                cursor: pointer;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
                font-family: inherit;
            }
            .mb-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.06);
                border-color: #cbd5e1;
            }
            .mb-title {
                color: #0f172a;
                font-weight: 600;
                font-size: 1.05rem;
            }
            .mb-sub {
                font-size: 0.85rem;
                color: #64748b;
                margin-top: 4px;
            }
        </style>

        <button class="mb-btn" id="mb-btn" onclick="launchMetabase()">
            <div class="mb-title" id="mb-title">Explore Database (Metabase)</div>
            <div class="mb-sub">/metabase-login</div>
        </button>

        <script>
        async function launchMetabase() {
            const btnTitle = document.getElementById("mb-title");
            btnTitle.innerText = "Authenticating...";

            try {
                const tokenRes = await window.parent.fetch("/metabase-login");
                if (!tokenRes.ok) throw new Error("Token request failed");
                const { session_id } = await tokenRes.json();

                await window.parent.fetch("/metabase/api/session", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id: session_id })
                });

                window.parent.open("/metabase", "_blank");
                btnTitle.innerText = "Explore Databases (Metabase)";
            } catch (err) {
                console.error("Auto-login error:", err);
                window.parent.open("/metabase-login", "_blank");
                btnTitle.innerText = "Explore Databases (Metabase)";
            }
        }
        </script>
        """
        components.html(metabase_card_html, height=85)

    with col_nav2:
        st.markdown(
            """
            <div class="nav-card">
                <a href="/airflow" target="_blank">View Workflows (Airflow)</a>
                <div class="nav-sub">/airflow</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_nav3:
        st.markdown(
            """
            <div class="nav-card">
                <a href="/marquez" target="_blank">Pipeline Lineage (Marquez)</a>
                <div class="nav-sub">/marquez</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # --- HIGH LEVEL                                                                SYSTEM METRICS ---
    st.subheader("📈 Database Totals")

    # Row 1: High Level Counts
    r1_col1, r1_col2, r1_col3 = st.columns(3)
    r1_col1.metric("Tables in Schema", f"{metrics.get('total_tables', 0):,}")
    r1_col2.metric("Unique Patients", f"{metrics.get('unique_patients', 0):,}")
    r1_col3.metric("Unique Claims", f"{metrics.get('unique_claims', 0):,}")

    # Row 2: Event Details & Total Rows
    r2_col1, r2_col2, r2_col3 = st.columns(3)
    r2_col1.metric("Unique Medications", f"{metrics.get('unique_medications', 0):,}")
    r2_col2.metric("Encounters + Procedures", f"{metrics.get('encounters_plus_procedures', 0):,}")
    r2_col3.metric("Total Rows (All Tables)", f"{metrics.get('total_rows', 0):,}")

    st.divider()

    # --- PATIENTS ADDED PER HOUR (+ rows overlay) ---
    st.subheader("⏱️ Patients Added Per Hour")

    df_hourly = load_hourly(cache_mtime)
    if not df_hourly.empty:
        df_hourly["hour"] = pd.to_datetime(df_hourly["hour"])
        # Hours with no loads show as 0 so the series is continuous
        full_range = pd.date_range(df_hourly["hour"].min(), df_hourly["hour"].max(), freq="h")
        df_hourly = (
            df_hourly.set_index("hour").reindex(full_range, fill_value=0)
            .rename_axis("hour").reset_index()
        )
        # Source hours are UTC; display in US Eastern (EST/EDT as appropriate)
        df_hourly["hour"] = (
            df_hourly["hour"].dt.tz_localize("UTC").dt.tz_convert("America/New_York").dt.tz_localize(None)
        )
        TZ_LABEL = pd.Timestamp(df_hourly["hour"].iloc[-1]).tz_localize("America/New_York").tzname()

        # Compact axis labels: 10k, 1.2k, 300M, 1.5B (full numbers stay in the tooltip)
        COMPACT_LABEL = (
            "datum.value >= 1e9 ? format(datum.value/1e9, '.2~f') + 'B' : "
            "datum.value >= 1e6 ? format(datum.value/1e6, '.1~f') + 'M' : "
            "datum.value >= 1e3 ? format(datum.value/1e3, '.1~f') + 'k' : "
            "format(datum.value, '~f')"
        )

        tooltip = [
            alt.Tooltip("hour:T", title=f"Hour ({TZ_LABEL})", format="%b %d, %I:00 %p"),
            alt.Tooltip("patients:Q", title="Patients added", format=","),
            alt.Tooltip("rows:Q", title="Rows added", format=","),
        ]
        base = alt.Chart(df_hourly).encode(
            x=alt.X(
                "hour:T",
                title=f"Hour ({TZ_LABEL})",
                axis=alt.Axis(
                    tickCount="day", format="%b %d", labelAngle=0, labelAlign="left",
                    labelFontWeight="bold", labelPadding=6, tickSize=10,
                    grid=False,
                ),
            )
        )
        bars = base.mark_bar(color="#2563eb", opacity=0.85).encode(
            y=alt.Y("patients:Q", title="Patients added",
                    axis=alt.Axis(titleColor="#2563eb", labelExpr=COMPACT_LABEL, orient="left", grid=False)),
            tooltip=tooltip,
        )
        st.altair_chart(
            bars.properties(height=320),
            width="stretch",
        )
    elif not df_trend.empty:
        # Fallback: older cache without hourly data
        st.caption("Hourly data not in cache yet; showing daily. Click Refresh.")
        df_trend["date"] = pd.to_datetime(df_trend["date"])
        df_trend = df_trend.sort_values("date").set_index("date").asfreq("D", fill_value=0)
        st.bar_chart(df_trend, y="count", height=300)
    else:
        st.info("No patient trend data available.")


# =====================================================================================
# AI CHAT SIDEBAR OPTIONS. Always rendered; CSS shows them only while the AI Chat tab is open.
# =====================================================================================
with st.sidebar.container(key="chatopts"):
    st.divider()
    st.markdown("#### 💵 Cost estimate")
    _tier = st.selectbox(
        "Compare against", list(CLOUD_PRICES), index=1, key="cloud_tier",
        help="Which paid Claude model to price this chat against (list prices per million tokens).",
    )
    _rin, _rout = CLOUD_PRICES[_tier]
    st.markdown(
        '<div style="font-size:0.85rem;opacity:0.7;line-height:1.5;padding-bottom:1.1rem">'
        f'In: &#36;{_rin / 1e6:.7f} / token<br>Out: &#36;{_rout / 1e6:.7f} / token</div>',
        unsafe_allow_html=True,
    )
    _cost = (st.session_state.get("cloud_in", 0) * _rin + st.session_state.get("cloud_out", 0) * _rout) / 1e6
    st.metric(
        "💵 Estimated cost (this chat)", _fmt_usd(_cost),
        help=f"What this conversation's tokens would cost on {_tier} at &#36;{_rin:.2f} in / &#36;{_rout:.2f} out per million tokens. "
             "Here there are no per-token fees, just electricity.",
    )
    st.markdown(
        '<div style="font-size:0.85rem;opacity:0.7;line-height:1.5">This conversation<br>'
        f'In: {st.session_state.get("cloud_in", 0):,} tokens<br>Out: {st.session_state.get("cloud_out", 0):,} tokens</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("#### 💬 Chat settings")
    st.select_slider(
        "🧠 Thinking effort",
        options=["Off", "Low", "Medium", "Max"],
        value=CHAT_DEFAULTS["chat_effort"],
        key="chat_effort",
        help="How hard the model reasons before answering. Off is fastest; Max thinks the longest.",
    )
    st.slider(
        "🌡️ Temperature", 0.0, 1.5, CHAT_DEFAULTS["chat_temp"], 0.05, key="chat_temp",
        help="Low = focused and predictable, high = more creative and random.",
    )
    st.slider(
        "🎯 Top-p", 0.1, 1.0, CHAT_DEFAULTS["chat_top_p"], 0.05, key="chat_top_p",
        help="Only sample from the smallest set of words whose probabilities add up to this value.",
    )
    if st.button("📝 System prompt", width="stretch"):
        _system_prompt_dialog()
    st.button("↩️ Reset chat settings", width="stretch", on_click=_reset_chat_opts)
