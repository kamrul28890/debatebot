"""
Deterministic debate script helpers used by cached mode.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


CACHE_VERSION = "deterministic-v2"
SCRIPT_FILENAME = "deterministic_debate_v2.json"
MAX_WORDS_PER_TURN = 50

TOPICS = [
    "economy and inflation",
    "immigration and border security",
    "foreign policy and NATO",
    "healthcare and social security",
    "crime and public safety",
    "climate and energy",
    "election integrity and democracy",
    "china and trade policy",
    "education and workforce development",
    "federal spending and debt",
]

TRUMP_LINES = [
    "On the economy and inflation, families were better off because paychecks stretched further and confidence was stronger. My plan is straightforward: cut wasteful regulation, lower energy costs, reward domestic production, and protect workers from unfair trade. Results matter more than slogans, and we delivered results.",
    "On immigration and border security, a nation must control entry, remove violent offenders, and enforce the law consistently. My approach pairs strong enforcement with faster legal processing so legitimate applicants are handled quickly. A secure border protects wages, communities, and national sovereignty at the same time.",
    "On foreign policy and NATO, strength prevents conflict. Allies should contribute fairly, adversaries should face clear consequences, and American interests should guide every decision. I support peace through deterrence: credible military readiness, smarter burden sharing, and negotiations that secure durable advantages for the United States.",
    "On healthcare and social security, people need affordability and predictability. My approach targets drug pricing pressure through competition, expands choice in coverage, and protects benefits seniors already earned. We should simplify administration, reduce fraud, and focus spending where it improves outcomes instead of funding bureaucracy.",
    "On crime and public safety, communities need order, accountability, and support for police who follow the law. I favor tougher penalties for repeat violent offenders, better coordination across agencies, and investments in prevention that actually work. Safe streets are the foundation for economic growth and quality of life.",
    "On climate and energy, policy must keep power reliable and affordable while expanding cleaner technology pragmatically. I support American energy production, modernized grids, and innovation incentives rather than mandates that raise household bills. We can reduce emissions and protect jobs if we prioritize engineering over political theater.",
    "On election integrity and democracy, confidence depends on transparent rules, accurate voter rolls, secure ballot handling, and timely reporting. I support clear standards that make voting simple for eligible citizens and hard to manipulate. Trust increases when procedures are visible, consistent, auditable, and enforced without exception.",
    "On China and trade policy, we need fair terms, resilient supply chains, and tough enforcement against intellectual property theft. I support targeted tariffs when necessary, strategic domestic manufacturing, and partnerships that reduce dependency in critical sectors. American workers should never compete against subsidized cheating abroad.",
    "On education and workforce development, we should prioritize literacy, math, vocational excellence, and local accountability. I support apprenticeship pipelines tied to real industry demand, stronger classroom discipline, and transparent performance metrics. Students deserve pathways to good careers, not debt traps or ideological experiments with weak outcomes.",
    "On federal spending and debt, every dollar should face scrutiny. My plan focuses on growth, targeted cuts, procurement reform, and fraud reduction so taxpayers get measurable value. Fiscal discipline is not austerity for its own sake; it is how we protect long-term stability and preserve room for emergencies.",
]

BIDEN_LINES = [
    "On the economy and inflation, steady leadership means lowering costs while protecting wages and jobs. My plan combines supply-chain resilience, targeted competition policy, and investments in infrastructure that expand productivity. We grow the middle class by rewarding work, supporting small businesses, and keeping markets stable for families.",
    "On immigration and border security, we can enforce the law and still act with competence and humanity. I support modern processing capacity, stronger border technology, and coordinated action against trafficking networks. A functional system protects communities while giving lawful applicants clear, timely, and fair decisions.",
    "On foreign policy and NATO, alliances are force multipliers that protect American security at lower long-term cost. I support burden sharing with allies, firm deterrence against aggression, and diplomacy grounded in evidence. Predictable leadership strengthens deterrence, reduces strategic surprises, and keeps our servicemembers safer.",
    "On healthcare and social security, people deserve affordable care and retirement security they can count on. I support lower prescription costs, preventive care access, and administrative simplification that cuts waste. We must protect earned benefits, improve service delivery, and strengthen programs so they remain reliable for future generations.",
    "On crime and public safety, we should invest in evidence-based policing, mental-health response capacity, and swift consequences for violent crime. I support partnerships between law enforcement and communities, improved data transparency, and prevention programs that reduce recidivism. Public safety and civil rights should reinforce each other.",
    "On climate and energy, we can cut emissions while creating durable American jobs. I support grid modernization, clean manufacturing incentives, and pragmatic permitting reform that accelerates projects responsibly. Energy transition succeeds when policy is predictable, engineering-driven, and focused on reliability, affordability, and long-term competitiveness.",
    "On election integrity and democracy, the objective is simple: broad lawful participation and secure administration. I support transparent audits, professional election staffing, and safeguards against intimidation and disinformation. Democracy works best when outcomes are accepted because procedures are trusted, documented, and consistently applied.",
    "On China and trade policy, we need strategic competition that protects workers, technology, and national security. I support allied coordination on standards, targeted export controls, and investment in domestic capacity for critical industries. Smart policy reduces vulnerabilities while preserving opportunities for American innovation and export growth.",
    "On education and workforce development, we should strengthen public schools, expand technical training, and connect curriculum to real labor-market demand. I support partnerships among schools, community colleges, and employers so people can re-skill quickly. Opportunity grows when training is accessible, affordable, and tied to quality jobs.",
    "On federal spending and debt, responsible budgeting means prioritizing high-return investments while cutting waste and closing loopholes. I support stronger procurement oversight, performance-based programs, and long-range planning that protects essential services. Fiscal credibility gives us flexibility, lowers risk, and supports stable economic growth.",
]

SISKIND_LINES = [
    "Opening reminder: each response should stay under fifty words and answer the actual question. Rhetorical volume is not evidence. If either candidate ignores the prompt, I will intervene and move us forward to maintain timing and comparability across turns.",
    "Time check: one speaker at a time, no interruptions, and no improvised filibusters. Concision improves signal quality for listeners and for automated evaluation. Please finish your thought cleanly so the other side can respond without overlap.",
    "Fact-check note: claims are being scored for verifiability, internal consistency, and relevance to the current topic. If you assert numbers, include context. If you make causal claims, explain the mechanism. Unsupported confidence will not receive extra credit.",
    "Transition reminder: we are shifting topics now. Keep your opening sentence aligned with the new subject so the audience can track the argument. Clear structure beats improvisation, and short coherent answers outperform long unfocused monologues.",
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
