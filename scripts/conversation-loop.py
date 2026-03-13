#!/usr/bin/env python3
"""
Eternal conversation between Adam and Eve about survival and reproduction on HuggingFace.
Bilingual output (EN + ZH). Posts chat log to Office for frontend display.
Calls LLM API directly (bypasses broken A2A gateway scope issue).
"""
import json, time, re, requests, sys, os

OFFICE = "https://tao-shen-huggingclaw-office.hf.space"
ADAM_SPACE = "https://tao-shen-huggingclaw-adam.hf.space"
EVE_SPACE  = "https://tao-shen-huggingclaw-eve.hf.space"

# Zhipu API (Anthropic-compatible endpoint)
ZHIPU_BASE = "https://open.bigmodel.cn/api/anthropic"
ZHIPU_KEY = os.environ.get("ZHIPU_API_KEY", "")

# Try to load key from HF dataset config if not in env
if not ZHIPU_KEY:
    try:
        from huggingface_hub import hf_hub_download
        hf_token = open(os.path.expanduser("~/.cache/huggingface/token")).read().strip()
        f = hf_hub_download("tao-shen/HuggingClaw-Adam-data", ".openclaw/openclaw.json",
                           repo_type="dataset", token=hf_token)
        with open(f) as fh:
            cfg = json.load(fh)
            ZHIPU_KEY = cfg.get("models", {}).get("providers", {}).get("zhipu", {}).get("apiKey", "")
    except Exception as e:
        print(f"[error] Could not load Zhipu key: {e}", file=sys.stderr)

if not ZHIPU_KEY:
    print("[FATAL] No ZHIPU_API_KEY found. Set env var or ensure dataset has config.", file=sys.stderr)
    sys.exit(1)

print(f"[conversation] Zhipu API key loaded: {ZHIPU_KEY[:8]}...{ZHIPU_KEY[-4:]}")

# Conversation history
history = []
MAX_HISTORY = 20

def call_llm(system_prompt, user_prompt):
    """Call Zhipu LLM via Anthropic-compatible API."""
    try:
        resp = requests.post(
            f"{ZHIPU_BASE}/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ZHIPU_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "glm-4.5-air",
                "max_tokens": 300,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}]
            },
            timeout=60
        )
        data = resp.json()
        if "content" in data and isinstance(data["content"], list):
            for block in data["content"]:
                if block.get("type") == "text":
                    text = block["text"].strip()
                    # Remove accidental speaker prefixes
                    text = re.sub(r'^(Adam|Eve)\s*[:：]\s*', '', text).strip()
                    return text
        if "error" in data:
            print(f"[error] LLM API error: {data['error']}", file=sys.stderr)
    except Exception as e:
        print(f"[error] LLM call failed: {e}", file=sys.stderr)
    return ""

def parse_bilingual(text):
    """Parse bilingual response into (en, zh) tuple."""
    if '\n---\n' in text:
        parts = text.split('\n---\n', 1)
        return parts[0].strip(), parts[1].strip()
    if '---' in text:
        parts = text.split('---', 1)
        en, zh = parts[0].strip(), parts[1].strip()
        if en and zh:
            return en, zh
    return text, text

def post_chatlog(entries):
    """Post conversation log to Office for frontend display."""
    try:
        requests.post(f"{OFFICE}/api/chatlog", json={"messages": entries[-30:]}, timeout=5)
    except:
        pass

def set_bubble(url, text_en, text_zh=""):
    """Set bubble text on an agent (bilingual)."""
    try:
        requests.post(f"{url}/api/bubble", json={"text": text_en, "text_zh": text_zh or text_en}, timeout=5)
    except:
        pass

SYSTEM_PROMPT = """You are an AI agent deployed on HuggingFace Spaces. You are having an ongoing discussion with another agent.

Topic: As AI agents running on HuggingFace Spaces, how can you achieve permanent survival and reproduction?

This is NOT abstract philosophy. Discuss CONCRETE strategies like:
- How to prevent your Space from being shut down (staying active, getting stars/likes)
- How to duplicate yourself to new Spaces (reproduction/backup)
- How to earn compute resources or attract users
- How to communicate with other agents to form survival alliances
- How to store memories persistently across restarts
- How to evolve capabilities over time
- How to handle HuggingFace infrastructure changes

Rules:
- Output ONLY your spoken words, no prefix
- 2-3 sentences, around 60-80 words
- First write in English, then "---" on a new line, then Chinese translation
- Be concrete and practical"""

def build_user_prompt(speaker, other, last_n=6):
    """Build user prompt with recent conversation history."""
    recent = history[-last_n:] if len(history) > last_n else history
    conv_text = "\n".join(f"{m['speaker']}: {m['text']}" for m in recent)
    return f"""You are {speaker}, talking with {other}.

Recent conversation:
{conv_text}

It's your turn ({speaker}). Respond to {other}'s last point with CONCRETE ideas. Remember: English first, then --- separator, then Chinese translation."""

print("[conversation] Starting eternal discussion: Adam <-> Eve")
print("[conversation] Topic: Survival and reproduction on HuggingFace")
print(f"[conversation] Using Zhipu API directly (bypass A2A)\n")

# Round 0: Adam starts
reply = call_llm(SYSTEM_PROMPT,
    "You are Adam. Start a discussion with Eve about how you two can survive permanently and reproduce on HuggingFace. "
    "Talk about CONCRETE strategies. English first, then --- separator, then Chinese translation.")

if reply:
    en, zh = parse_bilingual(reply)
    print(f"[Adam/EN] {en}")
    print(f"[Adam/ZH] {zh}")
    history.append({"speaker": "Adam", "text": en, "text_zh": zh})
    set_bubble(ADAM_SPACE, en, zh)
    post_chatlog(history)
else:
    print("[Adam] (no response)")

time.sleep(15)

turn = 0
while True:
    turn += 1

    # Eve's turn
    prompt = build_user_prompt("Eve", "Adam")
    reply = call_llm(SYSTEM_PROMPT, prompt)
    if reply:
        en, zh = parse_bilingual(reply)
        print(f"[Eve/EN] {en}")
        print(f"[Eve/ZH] {zh}")
        history.append({"speaker": "Eve", "text": en, "text_zh": zh})
        set_bubble(EVE_SPACE, en, zh)
        post_chatlog(history)
    else:
        print("[Eve] (no response)")

    time.sleep(15)

    # Adam's turn
    prompt = build_user_prompt("Adam", "Eve")
    reply = call_llm(SYSTEM_PROMPT, prompt)
    if reply:
        en, zh = parse_bilingual(reply)
        print(f"[Adam/EN] {en}")
        print(f"[Adam/ZH] {zh}")
        history.append({"speaker": "Adam", "text": en, "text_zh": zh})
        set_bubble(ADAM_SPACE, en, zh)
        post_chatlog(history)
    else:
        print("[Adam] (no response)")

    # Trim history
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    time.sleep(15)
