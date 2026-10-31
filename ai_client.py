import json
import time
import logging
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from config import load_config

# Silence the google-genai "AFC is not recommended" info banner on stdout/stderr.
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)

MODEL = "gemini-flash-latest"

_client: genai.Client | None = None
_client_key: str = ""


class QuotaExceeded(Exception):
    """Raised on HTTP 429 — the API key's rate/quota limit was hit."""
    def __init__(self, message: str, retry_after: float = 30.0):
        super().__init__(message)
        self.retry_after = retry_after


def get_client() -> genai.Client:
    global _client, _client_key
    config = load_config()
    key = config.get("google_api_key", "")
    if not key:
        raise ValueError("Google AI Studio API key not configured. Open Settings to add it.")
    if _client is None or _client_key != key:
        _client = genai.Client(api_key=key)
        _client_key = key
    return _client


def _generate_json(system: str, prompt: str, max_tokens: int, retries: int = 4) -> dict:
    client = get_client()
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        max_output_tokens=max_tokens,
        temperature=0.3,
        # Newer Gemini models "think" by default, consuming the output
        # budget before emitting text. Disable it for direct JSON replies.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=MODEL, contents=prompt, config=config
            )
            if not response.text:
                raise ValueError("Model returned an empty response.")
            return json.loads(response.text)
        except genai_errors.ClientError as e:
            # 429 = quota / rate limit. Not retryable here — surface it so the
            # caller can back off for the cooldown the server tells us.
            if getattr(e, "code", None) == 429:
                raise QuotaExceeded(str(e), _retry_after_seconds(e)) from e
            raise
        except genai_errors.ServerError as e:
            # 5xx (overload / temporary) — back off and retry.
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(
        "Gemini is temporarily unavailable (high demand). Please try again in a moment."
    ) from last_err


def _retry_after_seconds(err: Exception, default: float = 30.0) -> float:
    """Pull the 'retry in Ns' hint out of a 429 error message, if present."""
    import re
    m = re.search(r"retry in ([\d.]+)s", str(err))
    if m:
        try:
            return min(120.0, float(m.group(1)) + 1.0)
        except ValueError:
            pass
    return default


def improve_grammar(text: str, tone: str = "professional") -> dict:
    """Returns dict: improved, changes (list[str]), tone_score (int), has_errors (bool)."""
    tone_instructions = {
        "professional": "formal, clear, and business-appropriate",
        "casual": "friendly and conversational while remaining correct",
        "polite": "courteous, respectful, and considerate",
        "concise": "brief and direct, removing any unnecessary words",
    }
    tone_desc = tone_instructions.get(tone, tone_instructions["professional"])

    return _generate_json(
        system=(
            "You are a professional writing assistant. "
            "Always respond with valid JSON only, no markdown, no extra text."
        ),
        prompt=(
            f"Improve this text to be {tone_desc}. "
            "Fix grammar, spelling, punctuation, and improve clarity.\n\n"
            f'Text: """{text}"""\n\n'
            "Respond with JSON: "
            '{"improved": "...", "changes": ["change1", "change2"], '
            '"tone_score": 7, "has_errors": true}'
        ),
        max_tokens=1024,
    )


def live_check(text: str) -> dict:
    """Fast correctness-only check for the live desktop watcher.

    Returns dict: {"corrected": str, "has_errors": bool}.
    Preserves the writer's meaning, tone, and formatting — fixes only
    grammar, spelling, and punctuation. Does NOT rewrite for style.
    """
    max_tokens = min(2048, max(256, len(text) + 200))
    return _generate_json(
        system=(
            "You are a silent grammar and spelling corrector. "
            "Fix ONLY grammar, spelling, and punctuation mistakes. "
            "Preserve the original wording, meaning, tone, casing, emojis, "
            "and line breaks as much as possible — do not rewrite for style, "
            "do not add or remove sentences. If the text is already correct, "
            "return it unchanged with has_errors=false. "
            "Always respond with valid JSON only, no markdown, no extra text."
        ),
        prompt=(
            f'Text: """{text}"""\n\n'
            'Respond with JSON: {"corrected": "...", "has_errors": true}'
        ),
        max_tokens=max_tokens,
        retries=2,
    )


def generate_bug_report(prompt: str) -> dict:
    """Returns structured bug report dict."""
    return _generate_json(
        system=(
            "You are a QA engineer writing professional bug reports. "
            "Always respond with valid JSON only, no markdown, no extra text."
        ),
        prompt=(
            f'Generate a professional bug report from this description: """{prompt}"""\n\n'
            "Respond with JSON:\n"
            "{\n"
            '  "title": "concise bug title under 80 chars",\n'
            '  "description": "2-3 sentence detailed description",\n'
            '  "steps_to_reproduce": ["Step 1", "Step 2", "Step 3"],\n'
            '  "actual_result": "what actually happens",\n'
            '  "expected_result": "what should happen",\n'
            '  "severity": "Critical|High|Medium|Low",\n'
            '  "environment": "Browser/OS/version info to fill in",\n'
            '  "labels": ["label1", "label2"]\n'
            "}"
        ),
        max_tokens=2048,
    )
