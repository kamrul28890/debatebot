"""
src/brain/fact_checker.py

Real-time async fact-checker.
- Runs GPT-4-mini in a background thread (doesn't block debate)
- Emits a signal with verdict + real stat when done
- GUI hooks into the signal to flash the overlay
"""

import os
import sys
import threading
from typing import Callable, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import openai
import keys


FACT_CHECK_PROMPT = """You are a brutally accurate, nonpartisan debate fact-checker. 
You will be given a statement made during a presidential debate.

Analyze ONLY verifiable factual claims (statistics, dates, events, numbers).
Ignore opinions and predictions.

Respond ONLY in this exact JSON format (no markdown, no explanation outside the JSON):
{
  "has_claim": true/false,
  "verdict": "TRUE" / "FALSE" / "MISLEADING" / "UNVERIFIABLE",
  "claim": "the specific factual claim made",
  "real_stat": "the accurate fact or statistic (1 sentence)",
  "confidence": 0.0-1.0
}

If there is no verifiable factual claim, set has_claim to false and skip other fields.
Be harsh. Politicians lie constantly. When in doubt, mark MISLEADING.
Only mark TRUE if you are very confident it is accurate.
"""


class FactChecker:
    """
    Non-blocking fact checker. 
    Call check_async() and provide a callback — it will call you back when done.
    """

    def __init__(self):
        self.client = openai.AzureOpenAI(
            api_key=keys.azure_openai_key,
            api_version=keys.azure_openai_api_version,
            azure_endpoint=keys.azure_openai_endpoint,
        )
        # Use a cheaper/faster model for fact-checking to keep latency low
        # Fall back to main deployment if gpt-4o-mini isn't available
        self.deployment = getattr(keys, 'azure_openai_fast_deployment', keys.azure_openai_deployment)
        self.enabled = True

    def check_async(self, statement: str, speaker: str, callback: Callable):
        """
        Asynchronously fact-check a statement.
        Calls callback(result_dict) when done.
        result_dict keys: verdict, claim, real_stat, speaker, confidence
        """
        if not self.enabled or not statement.strip():
            return

        thread = threading.Thread(
            target=self._check_worker,
            args=(statement, speaker, callback),
            daemon=True,
        )
        thread.start()

    def _check_worker(self, statement: str, speaker: str, callback: Callable):
        try:
            import json

            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": FACT_CHECK_PROMPT},
                    {"role": "user", "content": f'{speaker.upper()} said: "{statement}"'},
                ],
                max_tokens=200,
                temperature=0.1,  # low temp for factual accuracy
            )

            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw.strip())

            if not result.get("has_claim", False):
                return  # No verifiable claim, skip overlay

            if result.get("confidence", 0) < 0.6:
                return  # Not confident enough, skip

            result["speaker"] = speaker
            callback(result)

        except Exception as e:
            print(f"[FactChecker Error] {e}")

    def toggle(self):
        self.enabled = not self.enabled
        return self.enabled


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time

    checker = FactChecker()

    def on_result(r):
        print(f"\n🔍 FACT CHECK RESULT:")
        print(f"   Speaker  : {r['speaker'].upper()}")
        print(f"   Claim    : {r['claim']}")
        print(f"   Verdict  : {r['verdict']}")
        print(f"   Real stat: {r['real_stat']}")
        print(f"   Confidence: {r['confidence']}")

    checker.check_async(
        "We had the greatest economy in the history of our country, with the best job numbers ever seen.",
        "trump",
        on_result,
    )

    print("Fact check running in background... (waiting 10s)")
    time.sleep(10)
