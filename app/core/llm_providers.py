import database


def _ollama_endpoint(settings: dict, path: str) -> str:
    base_url = (settings.get("ollama_base_url") or "http://localhost:11434").strip().rstrip("/")
    if base_url.endswith("/api"):
        return f"{base_url}{path}"
    return f"{base_url}/api{path}"


def _ollama_headers(settings: dict) -> dict[str, str]:
    api_key = (settings.get("ollama_api_key") or "").strip()
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}

async def _complete_openai(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("OpenAI API key not configured. Go to Settings → API Keys.")
    import openai

    client = openai.AsyncOpenAI(api_key=key)
    response = await client.chat.completions.create(**_chat_completion_args(model, system, user, temperature, max_tokens))
    return response.choices[0].message.content or ""


async def _complete_openrouter(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("OpenRouter API key not configured. Go to Settings -> API Keys.")
    import openai

    client = openai.AsyncOpenAI(
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "AI Blueprint",
        },
    )
    response = await client.chat.completions.create(**_chat_completion_args(model or "openrouter/auto", system, user, temperature, max_tokens))
    return response.choices[0].message.content or ""


async def _complete_xai(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("xAI API key not configured. Go to Settings -> API Keys.")
    import openai

    client = openai.AsyncOpenAI(api_key=key, base_url="https://api.x.ai/v1")
    response = await client.chat.completions.create(**_chat_completion_args(model or "grok-4.3", system, user, temperature, max_tokens))
    return response.choices[0].message.content or ""


async def _complete_gemini(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Google Gemini API key not configured. Go to Settings -> API Keys.")
    import httpx

    gemini_model = model or "gemini-2.5-flash"
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent",
            headers={"content-type": "application/json", "x-goog-api-key": key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
        )
        response.raise_for_status()
        data = response.json()
    parts = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if part.get("text"):
                parts.append(part["text"])
    return "".join(parts)


PERPLEXITY_PRESETS = {"fast-search", "pro-search", "deep-research", "advanced-deep-research"}


def _extract_response_text(data: dict) -> str:
    parts = []
    for output in data.get("output") or []:
        for content in output.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(content["text"])
    if parts:
        return "".join(parts)
    for choice in data.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(item.get("text", "") for item in content if isinstance(item, dict))
    return "".join(parts)


async def _complete_perplexity(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Perplexity API key not configured. Go to Settings -> API Keys.")
    import httpx

    model_id = model or "pro-search"
    payload = {
        "input": user,
        "instructions": system,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if model_id in PERPLEXITY_PRESETS:
        payload["preset"] = model_id
    else:
        payload["model"] = model_id

    async with httpx.AsyncClient(timeout=240) as client:
        response = await client.post(
            "https://api.perplexity.ai/v1/agent",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    return _extract_response_text(data)


async def _complete_mistral(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Mistral API key not configured. Go to Settings -> API Keys.")
    import httpx

    model_id = model or "mistral-medium-latest"
    if model_id.startswith("agent:"):
        response = await _complete_mistral_agent(key, model_id.removeprefix("agent:"), system, user, temperature, max_tokens)
        return response

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
    return _extract_response_text(data)


async def _complete_mistral_agent(key: str, agent_id: str, system: str, user: str, temperature: float, max_tokens: int) -> str:
    if not agent_id:
        raise RuntimeError("Mistral agent model IDs must use agent:<agent_id>.")
    import httpx

    async with httpx.AsyncClient(timeout=240) as client:
        response = await client.post(
            "https://api.mistral.ai/v1/agents/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "agent_id": agent_id,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
    return _extract_response_text(data)


def _uses_reasoning_chat_params(model: str) -> bool:
    model_id = (model or "").lower()
    return model_id.startswith(("gpt-5", "o1", "o3", "o4"))


def _chat_completion_args(model: str, system: str, user: str, temperature: float, max_tokens: int) -> dict:
    args = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if _uses_reasoning_chat_params(model):
        args["max_completion_tokens"] = max_tokens
        if (model or "").lower().startswith("gpt-5"):
            args["reasoning_effort"] = "none"
    else:
        args["temperature"] = temperature
        args["max_tokens"] = max_tokens
    return args


def _openai_assistants_model() -> str:
    model = database.get_setting("openai_assistants_model") or "gpt-4.1"
    if model.lower().startswith("gpt-5"):
        return "gpt-4.1"
    return model


async def _complete_openai_file_search(
    key: str, vector_store_id: str, system: str, user: str, model: str, temperature: float, max_tokens: int
) -> str:
    if not key:
        raise RuntimeError("OpenAI API key not configured. Go to Settings → API Keys.")
    import openai

    client = openai.AsyncOpenAI(api_key=key)
    assistant = await client.beta.assistants.create(
        name="AI Blueprint File Search Agent",
        model=_openai_assistants_model(),
        instructions=system,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
    )
    thread = await client.beta.threads.create(
        messages=[{"role": "user", "content": user}]
    )
    run = await client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    try:
        await client.beta.assistants.delete(assistant.id)
    except Exception:
        pass
    if run.status != "completed":
        raise RuntimeError(f"OpenAI file search agent did not complete: {run.status}")
    messages = await client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
    for msg in messages.data:
        if msg.role != "assistant":
            continue
        parts = []
        for block in msg.content or []:
            if getattr(block, "type", "") == "text":
                parts.append(block.text.value)
        return "\n".join(parts)
    return ""


async def _complete_groq(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Groq API key not configured.")
    from groq import AsyncGroq

    client = AsyncGroq(api_key=key)
    groq_model = model or "llama-3.1-8b-instant"
    response = await client.chat.completions.create(
        model=groq_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def _complete_anthropic(key: str, system: str, user: str, model: str, temperature: float, max_tokens: int) -> str:
    if not key:
        raise RuntimeError("Anthropic API key not configured.")
    import httpx

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model or "claude-3-5-sonnet-latest",
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")


async def _complete_ollama(system: str, user: str, model: str, temperature: float, max_tokens: int, settings: dict) -> str:
    import httpx

    chat_url = _ollama_endpoint(settings, "/chat")
    headers = _ollama_headers(settings)
    if "ollama.com" in chat_url and not headers:
        raise RuntimeError("Ollama API key is not configured. Add it in Settings -> API Keys -> Ollama.")

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            chat_url,
            headers=headers,
            json={
                "model": model or "llama3",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")
