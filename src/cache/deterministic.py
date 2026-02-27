"""
Deterministic debate script helpers used by cached mode.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


CACHE_VERSION = "deterministic-v3"
SCRIPT_FILENAME = "deterministic_debate_v2.json"
MAX_WORDS_PER_TURN = 60

TOPICS = [
    "economy, inflation, and wages",
    "immigration, border enforcement, and asylum policy",
    "healthcare affordability and prescription costs",
    "Ukraine, NATO, and broader war-risk management",
    "Epstein file transparency and accountability for elites",
    "Hunter Biden pardon ethics and DOJ independence",
    "Trump legal exposure, election integrity, and rule of law",
    "China competition, trade resilience, and national debt",
]

TRUMP_LINES = [
    "On the economy, families felt stronger purchasing power under my policies. We can lower costs by expanding domestic energy, cutting needless regulation, and rebuilding U.S. manufacturing capacity. Strong growth with real wages rising is how you restore confidence, and we have done it before.",
    "On border security, a country must enforce the law and remove violent offenders quickly. I support physical barriers where needed, stronger interior enforcement, and faster legal processing so lawful applicants are not trapped in a broken backlog. Security and fairness can coexist when rules are actually enforced.",
    "On healthcare, affordability starts with competition, pricing transparency, and cleaner administration. We should drive down drug costs, protect Medicare stability, and reduce fraud that drains resources from patients. You improve outcomes by rewarding value, not by adding layers of bureaucracy that delay care.",
    "On war and deterrence, peace comes from credible strength and clear red lines. Allies should contribute their fair share, and adversaries should know escalation carries real cost. Strategic ambiguity without readiness invites risk; disciplined leverage and burden sharing lower the chance of prolonged conflict.",
    "On the Epstein records, the public deserves legal transparency and equal enforcement without special treatment. Release what can be released lawfully, protect victims, and prosecute wrongdoing wherever evidence leads. Trust collapses when powerful networks appear insulated from accountability that ordinary citizens would face immediately.",
    "On the Hunter Biden pardon issue, the core question is institutional credibility. The Justice Department must be independent and visibly fair, and presidential actions should not look like family shielding. If people see double standards in sensitive cases, confidence in neutral law enforcement erodes quickly.",
    "On my own legal cases and election disputes, due process must be consistent and public. I will argue facts in court, challenge procedures lawfully, and accept transparent standards applied equally to everyone. Selective enforcement damages legitimacy more than any single verdict ever could.",
    "On China and debt, we need resilient supply chains, tougher IP enforcement, and strategic domestic industry investment. Trade policy should reward American production while reducing dependency in critical sectors. Fiscal discipline matters too, because persistent deficits weaken leverage and leave less room during true emergencies.",
]

BIDEN_LINES = [
    "On the economy, steady growth means lowering household costs while keeping jobs and wages resilient. We should strengthen supply chains, invest in productivity, and enforce fair competition so families see durable gains. Middle-class stability comes from predictable policy, not short-term volatility or headline theatrics.",
    "On immigration and the border, we can enforce the law while keeping the system functional and humane. I support modern processing capacity, anti-trafficking enforcement, and clear legal pathways that reduce chaos. Border order improves when Congress funds operations and stops using migration as campaign theater.",
    "On healthcare, people need affordable coverage and lower prescription costs without sacrificing quality. We should protect Medicare, expand preventive care, and simplify administration that wastes money and clinician time. Good policy is measurable: better outcomes, lower avoidable spending, and reliable access for working families.",
    "On wars abroad and alliances, partnerships reduce long-run risk and protect U.S. troops from larger future conflicts. We need credible deterrence, disciplined diplomacy, and burden sharing with NATO and regional partners. Security strategy should be evidence based, coordinated, and focused on preventing escalation.",
    "On Epstein-related accountability, the public deserves lawful disclosure, victim protection, and impartial prosecution based on evidence. No network of wealth or influence should distort investigative priorities. Institutions stay legitimate when cases are handled transparently, professionally, and insulated from political pressure or media speculation.",
    "On Hunter Biden and pardon ethics, the standard should be clear institutional independence and transparent reasoning. Any presidential action touching family must meet a high public-interest bar and withstand scrutiny. The broader lesson is strengthening guardrails so legal decisions remain trusted across administrations.",
    "On Trump legal cases and election integrity, everyone should receive due process under the same rules, no exceptions. We should protect voting access, secure administration, and factual public communication about outcomes. Democracy is strongest when disputes stay inside legal channels and evidence standards are respected.",
    "On China, trade, and debt, the right strategy combines allied coordination, targeted industrial policy, and domestic innovation capacity. We should protect critical technologies while keeping competitive export growth. Long-term fiscal credibility matters too, because sustainable budgets support national security and economic resilience.",
]

SISKIND_LINES = [
    "Format reminder: thirty-second alternating turns, no interruptions, and no evasive detours.",
    "Topic discipline matters. Begin with a direct answer, then defend it with evidence.",
    "Fact-checking is live. If you assert numbers, include context and mechanism.",
    "Transition now. Keep your first sentence aligned with the new topic.",
    "Closing reminder: concise, coherent answers outperform loud but unfocused monologues.",
]


def _normalize_turn(text: str) -> str:
    cleaned = " ".join((text or "").split())
    words = cleaned.split()
    if len(words) <= MAX_WORDS_PER_TURN:
        return cleaned
    clipped = " ".join(words[:MAX_WORDS_PER_TURN]).rstrip(" ,;:")
    if clipped and clipped[-1] not in ".!?":
        clipped += "."
    return clipped


def _cache_dir(base_dir: Path) -> Path:
    return base_dir / "data" / "cache_sessions"


def script_path(base_dir: Path) -> Path:
    return _cache_dir(base_dir) / SCRIPT_FILENAME


def build_script() -> dict:
    return {
        "version": CACHE_VERSION,
        "max_words": MAX_WORDS_PER_TURN,
        "turn_seconds": 30,
        "target_turns_per_persona": len(TRUMP_LINES),
        "topics": TOPICS,
        "trump": [_normalize_turn(line) for line in TRUMP_LINES],
        "biden": [_normalize_turn(line) for line in BIDEN_LINES],
        "siskind": [_normalize_turn(line) for line in SISKIND_LINES],
    }


def script_fingerprint(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_script(base_dir: Path) -> dict | None:
    path = script_path(base_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def ensure_script(base_dir: Path, force_rebuild: bool = False) -> dict:
    path = script_path(base_dir)
    if not force_rebuild and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") == CACHE_VERSION:
                return payload
        except Exception:
            pass

    payload = build_script()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
