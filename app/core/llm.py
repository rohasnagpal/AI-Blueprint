import asyncio
import threading

import database
from routes import councils as legacy_councils


def get_legacy_settings_with_secrets() -> dict:
    settings = database.get_all_settings()
    for key in database.API_KEY_FIELDS:
        settings[key] = database.get_setting(key)
    return settings


def configured_llm_provider(settings: dict) -> str | None:
    provider = settings.get("local_llm_provider", "openai")
    if provider == "openai" and settings.get("openai_api_key"):
        return provider
    if provider == "anthropic" and settings.get("anthropic_api_key"):
        return provider
    if provider == "groq" and settings.get("groq_api_key"):
        return provider
    if provider == "openrouter" and settings.get("openrouter_api_key"):
        return provider
    if provider == "gemini" and settings.get("gemini_api_key"):
        return provider
    if provider == "xai" and settings.get("xai_api_key"):
        return provider
    if provider == "ollama":
        return provider
    return None


def complete_with_configured_llm(settings: dict, system: str, user: str, *, model: str | None = None, temperature: float = 0.2, max_tokens: int = 2048) -> str | None:
    provider = configured_llm_provider(settings)
    if not provider:
        return None
    model_id = model or settings.get("chat_model", "gpt-4o")
    if provider == "openai":
        return run_async(legacy_councils._complete_openai(settings.get("openai_api_key", ""), system, user, model_id, temperature, max_tokens))
    if provider == "anthropic":
        return run_async(legacy_councils._complete_anthropic(settings.get("anthropic_api_key", ""), system, user, model_id, temperature, max_tokens))
    if provider == "groq":
        return run_async(legacy_councils._complete_groq(settings.get("groq_api_key", ""), system, user, model_id, temperature, max_tokens))
    if provider == "openrouter":
        return run_async(legacy_councils._complete_openrouter(settings.get("openrouter_api_key", ""), system, user, model_id, temperature, max_tokens))
    if provider == "gemini":
        return run_async(legacy_councils._complete_gemini(settings.get("gemini_api_key", ""), system, user, model_id, temperature, max_tokens))
    if provider == "xai":
        return run_async(legacy_councils._complete_xai(settings.get("xai_api_key", ""), system, user, model_id, temperature, max_tokens))
    if provider == "ollama":
        return run_async(legacy_councils._complete_ollama(system, user, model_id, temperature, max_tokens, settings))
    return None


async def complete_async(
    settings: dict,
    provider: str,
    system: str,
    user: str,
    *,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    if provider == "anthropic":
        return await legacy_councils._complete_anthropic(settings.get("anthropic_api_key", ""), system, user, model, temperature, max_tokens)
    if provider == "groq":
        return await legacy_councils._complete_groq(settings.get("groq_api_key", ""), system, user, model, temperature, max_tokens)
    if provider == "ollama":
        return await legacy_councils._complete_ollama(system, user, model, temperature, max_tokens, settings)
    if provider == "openrouter":
        return await legacy_councils._complete_openrouter(settings.get("openrouter_api_key", ""), system, user, model, temperature, max_tokens)
    if provider == "gemini":
        return await legacy_councils._complete_gemini(settings.get("gemini_api_key", ""), system, user, model, temperature, max_tokens)
    if provider == "xai":
        return await legacy_councils._complete_xai(settings.get("xai_api_key", ""), system, user, model, temperature, max_tokens)
    if provider == "openai_file_search":
        return await legacy_councils._complete_openai_file_search(
            settings.get("openai_api_key", ""),
            settings["vector_store_id"],
            system,
            user,
            model,
            temperature,
            max_tokens,
        )
    return await legacy_councils._complete_openai(settings.get("openai_api_key", ""), system, user, model, temperature, max_tokens)


def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")
