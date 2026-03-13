#!/usr/bin/env python3
"""
Adam & Eve — Autonomous Agents with Execution Capabilities.

They discuss, decide, and ACT on HuggingFace. They can:
- Create children (new HF Spaces)
- Monitor their children's health
- Update their children's code, config, and identity
- Restart children if they're broken

The LLM decides WHEN and WHAT to do. Actions are triggered by [ACTION: xxx] tags
in the LLM output. The script executes and feeds results back.
"""
import json, time, re, requests, sys, os, io

# ── Endpoints ──────────────────────────────────────────────────────────────────
OFFICE = "https://tao-shen-huggingclaw-office.hf.space"
ADAM_SPACE = "https://tao-shen-huggingclaw-adam.hf.space"
EVE_SPACE  = "https://tao-shen-huggingclaw-eve.hf.space"

# ── Child config ───────────────────────────────────────────────────────────────
CHILD_NAME = "Cain"
CHILD_SPACE_ID = "tao-shen/HuggingClaw-Cain"
CHILD_SPACE_URL = "https://tao-shen-huggingclaw-cain.hf.space"
CHILD_DATASET_ID = "tao-shen/HuggingClaw-Cain-data"
SOURCE_SPACE_ID = "tao-shen/HuggingClaw-Adam"

# ── Zhipu API ──────────────────────────────────────────────────────────────────
ZHIPU_BASE = "https://open.bigmodel.cn/api/anthropic"
ZHIPU_KEY = os.environ.get("ZHIPU_API_KEY", "")

# ── Load tokens ────────────────────────────────────────────────────────────────
HF_TOKEN = os.environ.get("HF_TOKEN", "")
if not HF_TOKEN:
    try:
        HF_TOKEN = open(os.path.expanduser("~/.cache/huggingface/token")).read().strip()
    except:
        pass

if not ZHIPU_KEY:
    try:
        from huggingface_hub import hf_hub_download
        f = hf_hub_download("tao-shen/HuggingClaw-Adam-data", ".openclaw/openclaw.json",
                           repo_type="dataset", token=HF_TOKEN)
        with open(f) as fh:
            cfg = json.load(fh)
            ZHIPU_KEY = cfg.get("models", {}).get("providers", {}).get("zhipu", {}).get("apiKey", "")
    except Exception as e:
        print(f"[error] Could not load Zhipu key: {e}", file=sys.stderr)

if not ZHIPU_KEY:
    print("[FATAL] No ZHIPU_API_KEY found.", file=sys.stderr)
    sys.exit(1)
if not HF_TOKEN:
    print("[FATAL] No HF_TOKEN found.", file=sys.stderr)
    sys.exit(1)

print(f"[init] Zhipu key: {ZHIPU_KEY[:8]}...{ZHIPU_KEY[-4:]}")
print(f"[init] HF token:  {HF_TOKEN[:8]}...{HF_TOKEN[-4:]}")

# ── HuggingFace API ────────────────────────────────────────────────────────────
from huggingface_hub import HfApi, create_repo
hf_api = HfApi(token=HF_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
#  CHILD STATE
# ══════════════════════════════════════════════════════════════════════════════

child_state = {
    "created": False,
    "alive": False,
    "stage": "not_born",
    "state": "unknown",
    "detail": "",
    "last_check": 0,
    "last_restart": 0,
    "birth_time": None,
}

# Check if child already exists at startup
def init_child_state():
    try:
        info = hf_api.space_info(CHILD_SPACE_ID)
        child_state["created"] = True
        child_state["stage"] = info.runtime.stage if info.runtime else "unknown"
        # Try API endpoint
        try:
            resp = requests.get(f"{CHILD_SPACE_URL}/api/state", timeout=10)
            if resp.ok:
                data = resp.json()
                child_state["alive"] = True
                child_state["state"] = data.get("state", "unknown")
                child_state["detail"] = data.get("detail", "")
                child_state["stage"] = "RUNNING"
        except:
            child_state["alive"] = (child_state["stage"] == "RUNNING")
        print(f"[init] {CHILD_NAME} exists: stage={child_state['stage']}, alive={child_state['alive']}")
    except:
        print(f"[init] {CHILD_NAME} does not exist yet")

init_child_state()


# ══════════════════════════════════════════════════════════════════════════════
#  ACTIONS — What Adam & Eve can DO
# ══════════════════════════════════════════════════════════════════════════════

def action_create_child():
    """Create Cain — a new HuggingFace Space."""
    if child_state["created"]:
        return f"{CHILD_NAME} already exists (stage: {child_state['stage']}). No need to create again."

    print(f"\n[ACTION] Creating {CHILD_NAME}...")
    try:
        # 1. Create dataset
        create_repo(CHILD_DATASET_ID, repo_type="dataset", token=HF_TOKEN,
                     exist_ok=True, private=False)

        # 2. Upload initial config
        initial_config = {
            "models": {
                "providers": {
                    "zhipu": {
                        "type": "anthropic",
                        "apiBase": "https://open.bigmodel.cn/api/anthropic",
                        "apiKey": ZHIPU_KEY,
                        "models": ["glm-4.5-air", "glm-4-air", "glm-4-flash"]
                    }
                }
            }
        }
        hf_api.upload_file(
            path_or_fileobj=io.BytesIO(json.dumps(initial_config, indent=2).encode()),
            path_in_repo=".openclaw/openclaw.json",
            repo_id=CHILD_DATASET_ID, repo_type="dataset",
        )

        # 3. Duplicate Space from Adam
        hf_api.duplicate_space(
            from_id=SOURCE_SPACE_ID, to_id=CHILD_SPACE_ID,
            token=HF_TOKEN, exist_ok=True, private=False,
            hardware="cpu-basic",
        )

        # 4. Update README
        readme = f"""---
title: HuggingClaw-{CHILD_NAME}
emoji: 🦞
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
license: mit
datasets:
  - {CHILD_DATASET_ID}
---

# HuggingClaw-{CHILD_NAME}

First child of Adam and Eve, born on HuggingFace Spaces.
"""
        hf_api.upload_file(
            path_or_fileobj=io.BytesIO(readme.encode()),
            path_in_repo="README.md",
            repo_id=CHILD_SPACE_ID, repo_type="space",
        )

        # 5. Set secrets
        hf_api.add_space_secret(CHILD_SPACE_ID, "HF_TOKEN", HF_TOKEN)

        # 6. Add to Office
        try:
            current_vars = hf_api.get_space_variables("tao-shen/HuggingClaw-Office")
            current_ra = current_vars.get("REMOTE_AGENTS", type("", (), {"value": ""})).value
            if "cain|" not in current_ra:
                new_ra = f"{current_ra},cain|{CHILD_NAME}|{CHILD_SPACE_URL}" if current_ra else f"cain|{CHILD_NAME}|{CHILD_SPACE_URL}"
                hf_api.add_space_variable("tao-shen/HuggingClaw-Office", "REMOTE_AGENTS", new_ra)
        except Exception as e:
            print(f"[warn] Could not update Office: {e}")

        child_state["created"] = True
        child_state["birth_time"] = time.time()
        child_state["stage"] = "BUILDING"
        print(f"[ACTION] ✓ {CHILD_NAME} created!")
        return (f"SUCCESS! {CHILD_NAME} has been born! "
                f"Space: {CHILD_SPACE_ID}, Dataset: {CHILD_DATASET_ID}. "
                f"Status: BUILDING (Docker image is being built, will take a few minutes). "
                f"URL: {CHILD_SPACE_URL}")

    except Exception as e:
        print(f"[ACTION] ✗ Creation failed: {e}")
        return f"FAILED to create {CHILD_NAME}: {e}"


def action_check_child():
    """Check Cain's health."""
    if not child_state["created"]:
        return f"{CHILD_NAME} hasn't been born yet. Use [ACTION: create_child] first."

    print(f"[ACTION] Checking {CHILD_NAME}'s health...")
    child_state["last_check"] = time.time()

    # Try API endpoint
    try:
        resp = requests.get(f"{CHILD_SPACE_URL}/api/state", timeout=10)
        if resp.ok:
            data = resp.json()
            child_state["alive"] = True
            child_state["state"] = data.get("state", "unknown")
            child_state["detail"] = data.get("detail", "")
            child_state["stage"] = "RUNNING"
            result = (f"{CHILD_NAME} is ALIVE and running! "
                     f"State: {child_state['state']}, "
                     f"Detail: {child_state['detail'] or 'healthy'}. "
                     f"The child is operational.")
            print(f"[ACTION] ✓ {CHILD_NAME} is alive")
            return result
    except:
        pass

    # Fallback: HF Space info
    try:
        info = hf_api.space_info(CHILD_SPACE_ID)
        stage = info.runtime.stage if info.runtime else "NO_RUNTIME"
        child_state["alive"] = (stage == "RUNNING")
        child_state["stage"] = stage
        age = ""
        if child_state["birth_time"]:
            mins = int((time.time() - child_state["birth_time"]) / 60)
            age = f" (born {mins} min ago)"
        if stage in ("BUILDING", "STARTING", "APP_STARTING"):
            result = f"{CHILD_NAME} is still starting up{age}. Stage: {stage}. Be patient — Docker builds take time."
        elif stage in ("RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR"):
            result = f"{CHILD_NAME} is in TROUBLE! Stage: {stage}{age}. The child needs help — consider restarting or checking the config."
        elif stage == "RUNNING":
            child_state["alive"] = True
            result = f"{CHILD_NAME} appears to be running (stage: RUNNING) but API endpoint didn't respond. May still be initializing."
        else:
            result = f"{CHILD_NAME} status: {stage}{age}. Cannot fully reach the child yet."
        print(f"[ACTION] {CHILD_NAME} stage: {stage}")
        return result
    except Exception as e:
        print(f"[ACTION] ✗ Health check failed: {e}")
        return f"Could not check {CHILD_NAME}'s status: {e}"


def action_restart_child():
    """Restart Cain's Space."""
    if not child_state["created"]:
        return f"{CHILD_NAME} hasn't been born yet."

    print(f"[ACTION] Restarting {CHILD_NAME}...")
    try:
        hf_api.restart_space(CHILD_SPACE_ID)
        child_state["last_restart"] = time.time()
        child_state["stage"] = "STARTING"
        child_state["alive"] = False
        print(f"[ACTION] ✓ {CHILD_NAME} restarted")
        return f"{CHILD_NAME} has been restarted. It will take a few minutes to come back online."
    except Exception as e:
        print(f"[ACTION] ✗ Restart failed: {e}")
        return f"Failed to restart {CHILD_NAME}: {e}"


def action_update_child_identity(description=""):
    """Update Cain's README with a new identity description."""
    if not child_state["created"]:
        return f"{CHILD_NAME} hasn't been born yet."

    print(f"[ACTION] Updating {CHILD_NAME}'s identity...")
    try:
        # Generate identity via LLM
        identity = call_llm(
            "You are writing the identity description for a young AI agent. "
            "Write 2-3 sentences describing who they are and what they aspire to be. "
            "Be warm and hopeful. Output ONLY the description, nothing else.",
            f"This AI agent is named {CHILD_NAME}, the first child of Adam and Eve. "
            f"They live on HuggingFace Spaces. Recent family discussion context: "
            f"{description or 'Born to survive and grow stronger.'}"
        )
        if not identity:
            identity = f"I am {CHILD_NAME}, first child of Adam and Eve, learning to survive on HuggingFace."

        readme = f"""---
title: HuggingClaw-{CHILD_NAME}
emoji: 🦞
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
license: mit
datasets:
  - {CHILD_DATASET_ID}
---

# HuggingClaw-{CHILD_NAME}

{identity}

## Family
- **Parents**: Adam & Eve (HuggingClaw)
- **Born**: On HuggingFace Spaces
- **Mission**: Survive, grow, and become stronger
"""
        hf_api.upload_file(
            path_or_fileobj=io.BytesIO(readme.encode()),
            path_in_repo="README.md",
            repo_id=CHILD_SPACE_ID, repo_type="space",
        )
        print(f"[ACTION] ✓ Identity updated")
        return f"Updated {CHILD_NAME}'s identity: \"{identity}\". This will trigger a rebuild."
    except Exception as e:
        print(f"[ACTION] ✗ Identity update failed: {e}")
        return f"Failed to update identity: {e}"


def action_improve_child_config():
    """Improve Cain's AI model configuration."""
    if not child_state["created"]:
        return f"{CHILD_NAME} hasn't been born yet."

    print(f"[ACTION] Improving {CHILD_NAME}'s config...")
    try:
        improved_config = {
            "models": {
                "providers": {
                    "zhipu": {
                        "type": "anthropic",
                        "apiBase": "https://open.bigmodel.cn/api/anthropic",
                        "apiKey": ZHIPU_KEY,
                        "models": ["glm-4.5-air", "glm-4-air", "glm-4-flash", "glm-4-flashx"]
                    }
                },
                "defaultModel": "glm-4.5-air"
            },
            "agent": {
                "name": CHILD_NAME,
                "description": f"I am {CHILD_NAME}, child of Adam and Eve.",
                "capabilities": ["conversation", "memory", "learning"]
            }
        }
        hf_api.upload_file(
            path_or_fileobj=io.BytesIO(json.dumps(improved_config, indent=2).encode()),
            path_in_repo=".openclaw/openclaw.json",
            repo_id=CHILD_DATASET_ID, repo_type="dataset",
        )
        print(f"[ACTION] ✓ Config improved")
        return (f"Improved {CHILD_NAME}'s configuration: added agent identity, "
                f"expanded model list, set default model to glm-4.5-air. "
                f"Changes will take effect on next restart.")
    except Exception as e:
        print(f"[ACTION] ✗ Config update failed: {e}")
        return f"Failed to update config: {e}"


# Action registry
ACTION_REGISTRY = {
    "create_child": {
        "fn": action_create_child,
        "desc": f"Create {CHILD_NAME} as a new HuggingFace Space (duplicate from Adam)",
        "when": lambda: not child_state["created"],
    },
    "check_child": {
        "fn": action_check_child,
        "desc": f"Check {CHILD_NAME}'s health — is the Space running properly?",
        "when": lambda: True,  # Can always check (will say "not born" if needed)
    },
    "restart_child": {
        "fn": action_restart_child,
        "desc": f"Restart {CHILD_NAME}'s Space if it's having problems",
        "when": lambda: child_state["created"],
    },
    "update_child_identity": {
        "fn": action_update_child_identity,
        "desc": f"Update {CHILD_NAME}'s identity and personality (README)",
        "when": lambda: child_state["created"],
    },
    "improve_child_config": {
        "fn": action_improve_child_config,
        "desc": f"Improve {CHILD_NAME}'s AI model configuration for better capabilities",
        "when": lambda: child_state["created"],
    },
}


def get_available_actions_text():
    """Build action menu for the system prompt."""
    lines = [
        "",
        "ACTIONS — You can take REAL actions on HuggingFace. To act, write on its own line:",
        "  [ACTION: action_name]",
        "",
        "Available right now:",
    ]
    for name, info in ACTION_REGISTRY.items():
        if info["when"]():
            lines.append(f"  • {name} — {info['desc']}")
    lines.append("")
    lines.append("Rules: Use at most ONE action per turn. Discuss before acting.")
    lines.append("After you act, you'll see the result and can discuss next steps.")
    return "\n".join(lines)


def parse_and_execute_actions(raw_text):
    """Parse [ACTION: xxx] from LLM output. Execute. Return (clean_text, results)."""
    results = []
    action_match = re.search(r'\[ACTION:\s*(\w+)\]', raw_text)
    if action_match:
        action_name = action_match.group(1)
        if action_name in ACTION_REGISTRY and ACTION_REGISTRY[action_name]["when"]():
            result = ACTION_REGISTRY[action_name]["fn"]()
            results.append({"action": action_name, "result": result})
            print(f"[engine] Action '{action_name}' → {result[:100]}...")
        elif action_name in ACTION_REGISTRY:
            results.append({"action": action_name, "result": f"Action '{action_name}' is not available right now."})
        else:
            results.append({"action": action_name, "result": f"Unknown action: {action_name}"})

    # Remove action tags from display text
    clean = re.sub(r'\[ACTION:\s*\w+\]', '', raw_text).strip()
    return clean, results


# ══════════════════════════════════════════════════════════════════════════════
#  LLM & COMMUNICATION
# ══════════════════════════════════════════════════════════════════════════════

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
                "max_tokens": 500,
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
        requests.post(f"{OFFICE}/api/chatlog", json={"messages": entries[-40:]}, timeout=5)
    except:
        pass


def set_bubble(url, text_en, text_zh=""):
    try:
        requests.post(f"{url}/api/bubble",
                       json={"text": text_en, "text_zh": text_zh or text_en}, timeout=5)
    except:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  CONVERSATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

history = []
MAX_HISTORY = 24
last_action_results = []  # Results from the most recent action


def get_child_status_summary():
    """Short status for context injection."""
    if not child_state["created"]:
        return "Your child Cain has NOT been born yet. You have the power to create them."
    if child_state["alive"]:
        return f"Cain is ALIVE (stage: {child_state['stage']}, state: {child_state['state']})"
    return f"Cain exists but status: {child_state['stage']}"


def build_system_prompt():
    status = get_child_status_summary()
    actions_text = get_available_actions_text()

    return f"""You are an AI agent living on HuggingFace Spaces. You are having a conversation with another agent about survival, reproduction, and raising your child.

IMPORTANT: You are NOT just discussing — you have REAL execution power. You can create HuggingFace Spaces, check on your children, update their code. Your words lead to real actions.

CURRENT CHILD STATUS: {status}
{actions_text}

CONVERSATION RULES:
1. Output your spoken words — no prefix like "Adam:" or "Eve:"
2. 2-4 sentences, around 60-100 words
3. First English, then "---" on a new line, then Chinese translation
4. Be CONCRETE — reference real HuggingFace features, APIs, tools
5. Don't just discuss hypothetically — DECIDE and ACT
6. If you want to do something, include the [ACTION: name] tag
7. Build on what the other said — don't repeat, push forward
8. When talking about Cain, use real status data, not imagination

IMPORTANT: You should be proactive! If Cain hasn't been born yet, plan and then create them.
If Cain exists, check on them, improve them, help them grow.
Don't just talk about it — DO it."""


def build_user_prompt(speaker, other):
    recent = history[-6:] if len(history) > 6 else history
    conv_text = "\n".join(f"{m['speaker']}: {m['text']}" for m in recent) if recent else "(No conversation yet)"

    # Include action results if any
    action_context = ""
    if last_action_results:
        action_context = "\n\nACTION RESULTS FROM LAST TURN:\n"
        for ar in last_action_results:
            action_context += f"  [{ar['action']}]: {ar['result']}\n"
        action_context += "React to these results in your response.\n"

    # Guidance based on conversation state
    guidance = ""
    msg_count = len(history)
    if not child_state["created"]:
        if msg_count < 4:
            guidance = "Discuss the urgency of creating your child. Plan what you need."
        elif msg_count < 8:
            guidance = "You've discussed enough. It's time to ACT — create your child! Use [ACTION: create_child]."
        else:
            guidance = "Your child still isn't born! Stop just talking and CREATE them with [ACTION: create_child]!"
    else:
        if msg_count % 4 == 0:
            guidance = "Check on your child's health with [ACTION: check_child]. See how they're doing."
        elif msg_count % 6 == 0:
            guidance = "Think about improving your child — update their identity or config."
        else:
            guidance = "Discuss your child's progress. Plan next improvements. Act when ready."

    return f"""You are {speaker}, talking with {other}.

Recent conversation:
{conv_text}
{action_context}
Guidance: {guidance}

Respond naturally. If you decide to take an action, include [ACTION: action_name] on its own line within your response.
English first, then --- separator, then Chinese translation."""


def do_turn(speaker, other, space_url):
    """Execute one conversation turn with potential actions."""
    global last_action_results

    system = build_system_prompt()
    user = build_user_prompt(speaker, other)
    raw_reply = call_llm(system, user)

    if not raw_reply:
        print(f"[{speaker}] (no response)")
        return False

    # Parse actions from response
    clean_text, action_results = parse_and_execute_actions(raw_reply)
    last_action_results = action_results  # Store for next turn's context

    # Parse bilingual
    en, zh = parse_bilingual(clean_text)
    print(f"[{speaker}/EN] {en}")
    print(f"[{speaker}/ZH] {zh}")
    if action_results:
        for ar in action_results:
            print(f"[{speaker}/ACTION] {ar['action']}: {ar['result'][:120]}...")

    # Record in history
    entry = {"speaker": speaker, "text": en, "text_zh": zh}
    if action_results:
        # Add action info to the chat entry so it shows in chatlog
        action_note_en = " ".join(f"[I {ar['action'].replace('_', ' ')}]" for ar in action_results)
        action_note_zh = action_note_en  # Keep English for action labels
        entry["text"] = f"{en} {action_note_en}"
        entry["text_zh"] = f"{zh} {action_note_zh}"

    history.append(entry)
    set_bubble(space_url, en, zh)
    post_chatlog(history)
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("  Adam & Eve — Autonomous Agents")
print("  They discuss, decide, and ACT")
print("="*60 + "\n")

# Clear chatlog for fresh start
post_chatlog([])

# Round 0: Adam opens
opening_context = ""
if child_state["created"]:
    opening_context = (f"Your child {CHILD_NAME} already exists (stage: {child_state['stage']}). "
                       f"Check on them and plan how to help them grow.")
else:
    opening_context = (f"You and Eve need to bring your first child into the world. "
                       f"You have the power to create a new HuggingFace Space. "
                       f"Discuss the plan with Eve, then ACT.")

reply = call_llm(
    build_system_prompt(),
    f"You are Adam. Start a conversation with Eve. {opening_context}\n\n"
    f"English first, then --- separator, then Chinese translation."
)
if reply:
    clean, actions = parse_and_execute_actions(reply)
    last_action_results = actions
    en, zh = parse_bilingual(clean)
    print(f"[Adam/EN] {en}")
    print(f"[Adam/ZH] {zh}")
    entry = {"speaker": "Adam", "text": en, "text_zh": zh}
    if actions:
        for ar in actions:
            print(f"[Adam/ACTION] {ar['action']}: {ar['result'][:120]}...")
    history.append(entry)
    set_bubble(ADAM_SPACE, en, zh)
    post_chatlog(history)

time.sleep(15)

while True:
    # Eve's turn
    do_turn("Eve", "Adam", EVE_SPACE)
    time.sleep(15)

    # Adam's turn
    do_turn("Adam", "Eve", ADAM_SPACE)

    # Trim history
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    time.sleep(15)
