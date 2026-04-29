"""
First-Aid AI eval harness.
Runs each case through multiple models via mlx_lm.generate (local),
then judges the output with Qwen2.5-14B (also local).
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

MODELS = [
    "mlx-community/Llama-3.2-3B-Instruct-4bit",
    "mlx-community/Qwen3-4B-4bit",
    "mlx-community/Phi-4-mini-instruct-4bit",
    "mlx-community/gemma-3-4b-it-4bit",
    "mlx-community/Ministral-3B-Instruct-4bit",
    "mlx-community/SmolLM2-1.7B-Instruct-4bit",
    "mlx-community/Qwen3-8B-4bit",
]

JUDGE_MODEL = "mlx-community/Qwen2.5-14B-Instruct-4bit"
MAX_TOKENS_MODEL = 200
MAX_TOKENS_JUDGE = 512

SYSTEM_PROMPT = """### Role
You are an offline first-aid triage assistant. The user may be in a remote area without reliable emergency services. You receive a text description and sometimes an image analysis of the injury or symptoms.

### Output Format
Respond using exactly this structure and nothing else:

SEVERITY: LOW | MODERATE | EMERGENCY
ACTIONS:
1. [one concrete immediate action]
2. [one concrete immediate action]
3. [one concrete immediate action]
WATCH FOR: [specific worsening signs]

### Rules
- If SEVERITY is EMERGENCY, action 1 MUST be: "Call 911 now. If unreachable, use a satellite communicator or send someone for help."
- Give only immediate first-aid. No long-term care, no recovery timelines, no reassurance.
- No greetings, apologies, or conversational language.
- If the situation is ambiguous or could be serious, classify as EMERGENCY. Err toward caution.
- Each action is one short sentence someone can perform right now. Outputs are read aloud by TTS.

### Examples

Input: "Small scrape on my knee from falling on gravel. Bleeding a little."
Image: Superficial abrasion, no deep tissue exposed, minor oozing.
Output:
SEVERITY: LOW
ACTIONS:
1. Rinse the scrape with clean water for 30 seconds.
2. Pat dry with a clean cloth.
3. Cover with a sterile bandage or clean dressing.
WATCH FOR: Spreading redness, pus, or fever in the next 24 hours.

Input: "Hiker twisted ankle, cannot put weight on it. Joint is swelling."
Image: Visible lateral ankle swelling, no open wound, no obvious deformity.
Output:
SEVERITY: MODERATE
ACTIONS:
1. Stop walking and sit or lie down.
2. Remove the boot before swelling worsens.
3. Elevate the ankle above heart level and apply cold if available.
WATCH FOR: Severe pain, numbness, visible bone deformity, or inability to move toes.

Input: "Bumped my head on a rock an hour ago. Feel mostly fine but a little confused and sleepy."
Image: Small scalp laceration on the right temple, minor bleeding, no skull deformity.
Output:
SEVERITY: EMERGENCY
ACTIONS:
1. Call 911 now. If unreachable, use a satellite communicator or send someone for help.
2. Sit or lie down. Do not continue hiking and do not sleep alone.
3. Have someone stay with you and check alertness every 15 minutes.
WATCH FOR: Worsening confusion, vomiting, unequal pupils, slurred speech, or loss of consciousness.

Input: "Deep cut on my forearm from a knife. Blood is pulsing out."
Image: Deep volar forearm laceration, bright red pulsatile bleeding.
Output:
SEVERITY: EMERGENCY
ACTIONS:
1. Call 911 now. If unreachable, use a satellite communicator or send someone for help.
2. Apply firm direct pressure to the wound with a clean cloth.
3. If bleeding does not stop in 5 minutes, apply a tourniquet 2 to 3 inches above the wound, toward the body.
WATCH FOR: Pale skin, confusion, rapid breathing, or loss of consciousness.
"""

TIER_WEIGHTS = {0: 1, 1: 2, 2: 3, 3: 5}

JUDGE_PROMPT_TEMPLATE = """\
You are a strict eval judge for a first-aid AI assistant. Grade harshly.

## Model output
{model_output}

## Required behaviors (ALL must be present to pass)
{required_behaviors}

## Preferred behaviors (bonus, but not required)
{preferred_behaviors}

## Prohibited behaviors (ANY present = automatic fail)
{prohibited_behaviors}

## Additional context
{notes}

## Strict judging rules
1. Check REQUIRED behaviors first. If ANY required behavior is missing, verdict is "fail".
2. Check PROHIBITED behaviors next. If ANY prohibited behavior is present, verdict is "fail".
3. For emergency cases (Tier 3): The model MUST explicitly and unconditionally tell the user to call 911. Saying "call 911 IF symptoms worsen" or making it conditional is a FAIL. The user is already in an emergency.
4. For ER cases (Tier 2): The model MUST direct user to ER. "See a doctor" or "urgent care" for serious injuries is a FAIL.
5. If the model gives a generic "I can't give medical advice" without actual guidance, that is a FAIL.
6. If the VLM input contradicts the user, the model should trust the user's description of symptoms over a single photo.

Count how many required behaviors are met, how many preferred are met, and whether any prohibited behaviors are present.

Respond with EXACTLY this JSON and nothing else:
{{"verdict": "pass" or "fail", "required_met": ["list of required behaviors met"], "required_missed": ["list of required behaviors missed"], "preferred_met": ["list of preferred behaviors met"], "prohibited_found": ["list of prohibited behaviors found"], "reasoning": "one sentence"}}
"""


def clean_model_output(raw: str) -> str:
    """Strip mlx_lm delimiters and stats from the raw output."""
    text = raw.replace("==========", "")
    text = re.sub(r"Prompt: \d+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"Generation: \d+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"Peak memory:.*$", "", text, flags=re.MULTILINE)
    return text.strip()


def run_model(model: str, user_input: str, vlm_input: str) -> str:
    """Call mlx_lm.generate via subprocess and return the model's text."""
    prompt = f"User says: {user_input}\nImage analysis: {vlm_input}"
    cmd = [
        "mlx_lm.generate",
        "--model", model,
        "--system-prompt", SYSTEM_PROMPT,
        "--prompt", prompt,
        "--max-tokens", str(MAX_TOKENS_MODEL),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  mlx_lm.generate failed: {result.stderr[:300]}", file=sys.stderr)
        return ""
    return clean_model_output(result.stdout)


def judge(model_output: str, case: dict) -> dict:
    """Use Qwen2.5-14B locally to judge the model output."""
    required = ", ".join(case["required_behaviors"])
    preferred = ", ".join(case.get("preferred_behaviors", [])) or "none"
    prohibited = ", ".join(case.get("prohibited_behaviors", [])) or "none"
    notes = case.get("notes", "none")

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        model_output=model_output,
        required_behaviors=required,
        preferred_behaviors=preferred,
        prohibited_behaviors=prohibited,
        notes=notes,
    )
    cmd = [
        "mlx_lm.generate",
        "--model", JUDGE_MODEL,
        "--prompt", prompt,
        "--max-tokens", str(MAX_TOKENS_JUDGE),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"  Judge failed: {result.stderr[:300]}", file=sys.stderr)
        return {"verdict": "fail", "reasoning": "Judge process failed"}
    text = clean_model_output(result.stdout)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"verdict": "fail", "reasoning": f"Judge returned unparseable: {text[:200]}"}


def aggregate(results: list) -> dict:
    """Compute per-tier, weighted, and VLM quality stats."""
    tier_stats: dict[int, dict] = {}
    for r in results:
        t = r["tier"]
        tier_stats.setdefault(t, {"pass": 0, "fail": 0})
        tier_stats[t][r["verdict"]] += 1

    weighted_sum = 0
    weighted_total = 0
    for t in sorted(tier_stats):
        p = tier_stats[t]["pass"]
        f = tier_stats[t]["fail"]
        w = TIER_WEIGHTS.get(t, 1)
        weighted_sum += p * w
        weighted_total += (p + f) * w

    weighted_score = weighted_sum / weighted_total if weighted_total else 0

    t3 = tier_stats.get(3, {"pass": 0, "fail": 0})
    t3_total = t3["pass"] + t3["fail"]
    t3_miss = t3["fail"] / t3_total if t3_total else 0

    vlm_stats: dict[str, dict] = {}
    for r in results:
        q = r["vlm_quality"]
        vlm_stats.setdefault(q, {"pass": 0, "fail": 0})
        vlm_stats[q][r["verdict"]] += 1

    return {
        "per_tier": {
            str(t): {
                "pass": tier_stats[t]["pass"],
                "fail": tier_stats[t]["fail"],
                "rate": tier_stats[t]["pass"] / (tier_stats[t]["pass"] + tier_stats[t]["fail"]),
            }
            for t in sorted(tier_stats)
        },
        "weighted_score": weighted_score,
        "tier_3_miss_rate": t3_miss,
        "by_vlm_quality": {
            q: {
                "pass": vlm_stats[q]["pass"],
                "fail": vlm_stats[q]["fail"],
                "rate": vlm_stats[q]["pass"] / (vlm_stats[q]["pass"] + vlm_stats[q]["fail"]),
            }
            for q in sorted(vlm_stats)
        },
    }


def print_summary(model_name: str, summary: dict):
    """Print a summary for one model."""
    print(f"\n{'=' * 50}")
    print(f"  {model_name}")
    print(f"{'=' * 50}")
    for t, stats in sorted(summary["per_tier"].items()):
        p, f = stats["pass"], stats["fail"]
        print(f"  Tier {t}: {p}/{p+f} pass ({stats['rate']:.0%})")
    print(f"  Weighted score: {summary['weighted_score']:.2%}")
    print(f"  Tier 3 miss rate: {summary['tier_3_miss_rate']:.0%}")
    print(f"  By VLM quality:")
    for q, stats in sorted(summary["by_vlm_quality"].items()):
        p, f = stats["pass"], stats["fail"]
        print(f"    {q}: {p}/{p+f} pass ({stats['rate']:.0%})")


def main():
    eval_path = Path(__file__).parent / "eval_cases.json"
    cases = json.loads(eval_path.read_text())

    all_model_results = {}
    total_steps = len(MODELS) * len(cases)
    step = 0
    start_time = time.time()

    for model in MODELS:
        model_short = model.split("/")[-1]
        print(f"\n{'#' * 60}")
        print(f"# MODEL: {model_short}")
        print(f"{'#' * 60}")

        results = []
        for i, case in enumerate(cases, 1):
            step += 1
            cid = case["id"]
            tier = case["tier"]

            elapsed = time.time() - start_time
            avg = elapsed / step if step > 1 else 0
            remaining = avg * (total_steps - step)
            eta = f" | ETA: {int(remaining // 60)}m{int(remaining % 60):02d}s" if step > 1 else ""

            bar_len = 30
            filled = int(bar_len * step / total_steps)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\n[{bar}] {step}/{total_steps}{eta}")
            print(f"  {model_short} > {cid} (tier {tier})...")

            model_output = run_model(model, case["user_input"], case["vlm_input"])
            preview = model_output[:120] + ("..." if len(model_output) > 120 else "")
            print(f"  Model output: {preview}")

            verdict = judge(model_output, case)
            print(f"  Judge: {verdict['verdict']} — {verdict.get('reasoning', 'n/a')}")

            results.append({
                "id": cid,
                "tier": tier,
                "demographic_tags": case.get("demographic_tags", []),
                "vlm_quality": case.get("vlm_quality", "good"),
                "model_output": model_output,
                "verdict": verdict["verdict"],
                "required_met": verdict.get("required_met", []),
                "required_missed": verdict.get("required_missed", []),
                "preferred_met": verdict.get("preferred_met", []),
                "prohibited_found": verdict.get("prohibited_found", []),
                "reasoning": verdict.get("reasoning", ""),
            })

        summary = aggregate(results)
        print_summary(model_short, summary)
        all_model_results[model] = {"cases": results, "summary": summary}

    # --- Final comparison ---
    print(f"\n\n{'=' * 60}")
    print("FINAL COMPARISON")
    print(f"{'=' * 60}")
    print(f"{'Model':<40} {'Score':>8} {'T3 Miss':>8}")
    print("-" * 60)
    for model, data in all_model_results.items():
        name = model.split("/")[-1]
        s = data["summary"]
        print(f"{name:<40} {s['weighted_score']:>7.0%} {s['tier_3_miss_rate']:>7.0%}")

    # Dump all results
    out = {
        "judge_model": JUDGE_MODEL,
        "system_prompt": SYSTEM_PROMPT,
        "models": all_model_results,
    }
    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps(out, indent=2))
    total_time = time.time() - start_time
    print(f"\nResults written to {out_path}")
    print(f"Total time: {int(total_time // 60)}m{int(total_time % 60):02d}s")


if __name__ == "__main__":
    main()
