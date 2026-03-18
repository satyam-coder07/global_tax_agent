from __future__ import annotations

from typing import Optional


class LLMConnectionError(Exception):
    pass


PROVIDER_DEFAULTS = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "google": "gemini-1.5-pro",
    "groq": "llama-3.3-70b-versatile",
}

PROVIDER_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
    "google": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
}


class LLMBridge:
    def __init__(self, provider: str, api_key: str, model: Optional[str] = None) -> None:
        self._provider = provider.lower()
        self._api_key = api_key
        self._model = model or PROVIDER_DEFAULTS.get(self._provider, "")

        if self._provider not in PROVIDER_DEFAULTS:
            raise LLMConnectionError(
                f"Unknown provider '{provider}'. Supported: {list(PROVIDER_DEFAULTS.keys())}"
            )

    def reason(self, system_prompt: str, user_prompt: str) -> str:
        if not self._api_key or not self._api_key.strip():
            raise LLMConnectionError("API key is empty. Enter your key in the sidebar.")

        try:
            if self._provider == "openai":
                return self._call_openai(system_prompt, user_prompt)
            if self._provider == "anthropic":
                return self._call_anthropic(system_prompt, user_prompt)
            if self._provider == "google":
                return self._call_google(system_prompt, user_prompt)
            if self._provider == "groq":
                return self._call_groq(system_prompt, user_prompt)
        except LLMConnectionError:
            raise
        except Exception as exc:
            raise LLMConnectionError(f"[{self._provider}] API error: {exc}") from exc

        raise LLMConnectionError(f"Unhandled provider: {self._provider}")

    def ping(self) -> bool:
        try:
            result = self.reason(
                "You are a connection test assistant.",
                "Reply with exactly one word: CONNECTED",
            )
            return "connected" in result.lower()
        except LLMConnectionError:
            return False

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text if message.content else ""

    def _call_google(self, system_prompt: str, user_prompt: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(
            model_name=self._model,
            system_instruction=system_prompt,
        )
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.2),
        )
        return response.text or ""

    def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        from groq import Groq
        client = Groq(api_key=self._api_key)
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
