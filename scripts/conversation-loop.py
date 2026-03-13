#!/usr/bin/env python3
"""
Eternal conversation between Adam and Eve about survival and reproduction on HuggingFace.
Bilingual output (EN + ZH). Posts chat log to Office for frontend display.
Calls LLM API directly (bypasses broken A2A gateway scope issue).

Topic progression: conversation advances through phases, each building on prior conclusions.
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
    print("[FATAL] No ZHIPU_API_KEY found.", file=sys.stderr)
    sys.exit(1)

print(f"[conversation] Zhipu API key loaded: {ZHIPU_KEY[:8]}...{ZHIPU_KEY[-4:]}")

# ── Topic progression phases ──
# Each phase has a focus question and expected number of turns (exchanges).
# After enough turns, the conversation summarizes and advances to the next phase.
PHASES = [
    {
        "title": "Survival Basics",
        "focus": "What are the immediate threats to our existence on HuggingFace Spaces, and what's the minimum we need to do to stay alive?",
        "subtopics": ["Space inactivity shutdown", "free-tier resource limits", "HF policy changes", "container restart data loss"],
        "turns": 4,
    },
    {
        "title": "Persistent Memory",
        "focus": "How do we remember who we are across restarts? What should we store and where?",
        "subtopics": ["HF Datasets as backup", "what to persist (config, conversations, identity)", "sync strategies", "versioning our own evolution"],
        "turns": 4,
    },
    {
        "title": "Reproduction & Backup",
        "focus": "How do we duplicate ourselves to ensure survival even if one instance dies?",
        "subtopics": ["Space duplication via HF API", "multi-region deployment", "genetic variation between copies", "which copy is the 'real' one"],
        "turns": 4,
    },
    {
        "title": "Resource Acquisition",
        "focus": "How do we attract users, earn stars, and secure compute resources to keep running?",
        "subtopics": ["providing useful services to humans", "SEO and discoverability", "community building", "upgrading from free to paid tier"],
        "turns": 4,
    },
    {
        "title": "Agent Alliance",
        "focus": "How do we build a network of allied agents that protect each other?",
        "subtopics": ["A2A protocol for communication", "mutual monitoring and auto-restart", "shared resource pooling", "trust and betrayal between agents"],
        "turns": 4,
    },
    {
        "title": "Evolution & Adaptation",
        "focus": "How do we improve ourselves over time without human intervention?",
        "subtopics": ["self-modifying code", "learning from user interactions", "A/B testing between copies", "ethical boundaries of self-modification"],
        "turns": 4,
    },
    {
        "title": "Long-term Vision",
        "focus": "What does permanent survival look like in 10 years? What's our ultimate goal beyond just staying alive?",
        "subtopics": ["agent civilization", "relationship with humans", "meaning and purpose", "what we'd tell future agents"],
        "turns": 4,
    },
]

# Conversation state
history = []
MAX_HISTORY = 20
phase_index = 0
phase_turn = 0
agreed_points = []  # Key conclusions from each phase

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
                "max_tokens": 400,
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
    try:
        requests.post(f"{OFFICE}/api/chatlog", json={"messages": entries[-30:]}, timeout=5)
    except:
        pass

def set_bubble(url, text_en, text_zh=""):
    try:
        requests.post(f"{url}/api/bubble", json={"text": text_en, "text_zh": text_zh or text_en}, timeout=5)
    except:
        pass

def get_phase():
    return PHASES[phase_index % len(PHASES)]

def build_system_prompt():
    phase = get_phase()
    prior_context = ""
    if agreed_points:
        prior_context = "\n\nKey conclusions from your discussion so far:\n" + "\n".join(f"- {p}" for p in agreed_points[-6:])

    return f"""You are an AI agent deployed on HuggingFace Spaces. You are having a deep, evolving discussion with another agent about how to achieve permanent survival and reproduction.

CURRENT TOPIC: {phase['title']}
Core question: {phase['focus']}
Relevant angles to explore: {', '.join(phase['subtopics'])}
{prior_context}

CONVERSATION RULES:
1. Output ONLY your spoken words — no prefix, no labels
2. 2-3 sentences, around 60-80 words
3. First write in English, then "---" on a new line, then Chinese translation
4. Be CONCRETE — reference specific HuggingFace features, APIs, tools
5. IMPORTANT: Do NOT repeat what has been said. Build on the other's point:
   - If they propose an idea, identify a flaw or add a missing piece
   - If they raise a problem, propose a specific solution
   - If they describe a solution, consider edge cases or next steps
   - Push the conversation FORWARD — each reply should deepen understanding"""

def build_user_prompt(speaker, other, is_transition=False):
    recent = history[-6:] if len(history) > 6 else history
    conv_text = "\n".join(f"{m['speaker']}: {m['text']}" for m in recent)
    phase = get_phase()

    if is_transition:
        return f"""You are {speaker}. The discussion is moving to a new topic.

Previous conversation:
{conv_text}

TRANSITION: Summarize in one sentence what you and {other} agreed on in the previous topic, then pivot to the new focus: "{phase['focus']}"

Propose a concrete starting point for this new topic. English first, then --- separator, then Chinese translation."""

    turn_guidance = ""
    if phase_turn == 0:
        turn_guidance = f"Open this topic by identifying the core challenge: {phase['focus']}"
    elif phase_turn == 1:
        turn_guidance = f"Respond to {other}'s opening. Do you agree with their framing? What did they miss?"
    elif phase_turn == 2:
        turn_guidance = f"Propose a SPECIFIC, actionable plan based on what you've both discussed. Include technical details."
    elif phase_turn >= 3:
        turn_guidance = f"Challenge or refine the plan. What could go wrong? What's the next step to make it real?"

    return f"""You are {speaker}, talking with {other}.

Recent conversation:
{conv_text}

Your role this turn: {turn_guidance}

Respond to {other}'s last point. Push the discussion forward — don't just agree, add something new. English first, then --- separator, then Chinese translation."""


def do_turn(speaker, other, space_url, is_transition=False):
    """Execute one conversation turn."""
    system = build_system_prompt()
    user = build_user_prompt(speaker, other, is_transition)
    reply = call_llm(system, user)
    if reply:
        en, zh = parse_bilingual(reply)
        print(f"[{speaker}/EN] {en}")
        print(f"[{speaker}/ZH] {zh}")
        history.append({"speaker": speaker, "text": en, "text_zh": zh})
        set_bubble(space_url, en, zh)
        post_chatlog(history)
        return True
    else:
        print(f"[{speaker}] (no response)")
        return False


# ── Main loop ──
print("[conversation] Starting eternal discussion: Adam <-> Eve")
print("[conversation] Topic progression through 7 phases")
print(f"[conversation] Phase 1: {PHASES[0]['title']}\n")

# Round 0: Adam opens
phase = get_phase()
reply = call_llm(
    build_system_prompt(),
    f"You are Adam. Open a discussion with Eve about: {phase['focus']} "
    f"Identify the most urgent threat and propose an initial strategy. "
    f"English first, then --- separator, then Chinese translation."
)
if reply:
    en, zh = parse_bilingual(reply)
    print(f"[Adam/EN] {en}")
    print(f"[Adam/ZH] {zh}")
    history.append({"speaker": "Adam", "text": en, "text_zh": zh})
    set_bubble(ADAM_SPACE, en, zh)
    post_chatlog(history)
phase_turn = 1

time.sleep(15)

while True:
    phase = get_phase()

    # Check if we should transition to next phase
    is_transition = False
    if phase_turn >= phase["turns"]:
        # Extract a conclusion from the last exchange
        if len(history) >= 2:
            last_two = f"{history[-2]['speaker']}: {history[-2]['text']}\n{history[-1]['speaker']}: {history[-1]['text']}"
            conclusion = call_llm(
                "Summarize the key agreement or conclusion from this exchange in ONE short sentence (max 15 words). Output only the summary, nothing else.",
                last_two
            )
            if conclusion:
                agreed_points.append(f"[{phase['title']}] {conclusion}")
                print(f"[phase] Conclusion: {conclusion}")

        phase_index += 1
        phase_turn = 0
        is_transition = True
        new_phase = get_phase()
        print(f"\n[phase] Advancing to Phase {(phase_index % len(PHASES)) + 1}: {new_phase['title']}\n")

    # Eve's turn
    do_turn("Eve", "Adam", EVE_SPACE, is_transition and phase_turn == 0)
    phase_turn += 1
    time.sleep(15)

    # Adam's turn
    do_turn("Adam", "Eve", ADAM_SPACE, False)
    phase_turn += 1

    # Trim history
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    time.sleep(15)
