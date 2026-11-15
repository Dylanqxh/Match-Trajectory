"""Small protocol boundary for OpenAI-compatible and Anthropic-native APIs."""
import json


def is_anthropic(config) -> bool:
    return config.provider == "anthropic"


def is_responses(config) -> bool:
    return config.provider == "custom" and config.protocol == "responses"


def normalize_endpoint(base_url: str, protocol: str = "openai_compatible") -> str:
    """Resolve a configured base URL to the exact text-completion endpoint."""
    base = base_url.rstrip("/")
    suffixes = {
        "anthropic": "/messages",
        "openai_compatible": "/chat/completions",
        "responses": "/responses",
    }
    if protocol not in suffixes:
        raise ValueError("unsupported provider protocol")
    suffix = suffixes[protocol]
    if base.endswith(suffix):
        return base
    for existing in suffixes.values():
        if base.endswith(existing):
            base = base[:-len(existing)].rstrip("/")
            break
    return base + suffix


def request_endpoint(config) -> str:
    protocol = "anthropic" if is_anthropic(config) else "responses" if is_responses(config) else "openai_compatible"
    return normalize_endpoint(config.base_url, protocol)


def request_headers(config) -> dict[str, str]:
    secret = config.api_key.get_secret_value()
    if is_anthropic(config):
        return {"x-api-key": secret, "anthropic-version": "2023-06-01"}
    return {"Authorization": "Bearer " + secret}


def adapt_request(config, payload: dict) -> dict:
    """Convert the application's OpenAI-shaped request to the selected wire format."""
    if is_responses(config):
        excluded = {
            "messages", "max_tokens", "tools", "tool_choice", "response_format",
            "seed", "thinking", "temperature", "stream",
        }
        adapted = {key: value for key, value in payload.items() if key not in excluded}
        adapted["input"] = []
        for message in payload.get("messages") or []:
            content = message.get("content")
            if isinstance(content, list):
                blocks = []
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        blocks.append({"type": "input_text", "text": block["text"]})
                    elif isinstance(block, str):
                        blocks.append({"type": "input_text", "text": block})
            else:
                blocks = [{"type": "input_text", "text": str(content or "")}]
            adapted["input"].append({"role": message.get("role", "user"), "content": blocks})
        if "max_tokens" in payload:
            adapted["max_output_tokens"] = payload["max_tokens"]
        tools = payload.get("tools") or []
        if tools:
            adapted["tools"] = [{
                "type": "function",
                "name": row["function"]["name"],
                "description": row["function"].get("description", ""),
                "parameters": row["function"]["parameters"],
            } for row in tools if row.get("type") == "function"]
        choice = payload.get("tool_choice")
        if isinstance(choice, dict) and choice.get("type") == "function":
            adapted["tool_choice"] = {"type": "function", "name": choice["function"]["name"]}
        adapted["store"] = False
        return adapted
    if not is_anthropic(config):
        return payload
    adapted = {key: value for key, value in payload.items() if key not in {
        "messages", "tools", "tool_choice", "parallel_tool_calls", "response_format",
        "seed", "thinking", "temperature",
    }}
    messages = payload.get("messages") or []
    system = "\n".join(str(row.get("content") or "") for row in messages if row.get("role") == "system").strip()
    adapted["messages"] = [row for row in messages if row.get("role") != "system"]
    if system:
        adapted["system"] = system
    tools = payload.get("tools") or []
    if tools:
        adapted["tools"] = [{
            "name": row["function"]["name"],
            "description": row["function"].get("description", ""),
            "input_schema": row["function"]["parameters"],
        } for row in tools if row.get("type") == "function"]
    choice = payload.get("tool_choice")
    if isinstance(choice, dict) and choice.get("type") == "function":
        adapted["tool_choice"] = {"type": "tool", "name": choice["function"]["name"]}
    return adapted


def decode_response(config, body: bytes | bytearray) -> dict:
    """Normalize an API response to the existing Chat Completions envelope."""
    envelope = json.loads(body)
    if is_responses(config):
        output = envelope.get("output") or []
        text_parts = []
        tool_calls = []
        refused = False
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for block in item.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                    elif block.get("type") == "refusal":
                        refused = True
            elif item.get("type") == "function_call":
                arguments = item.get("arguments", "{}")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments if isinstance(arguments, dict) else {}, ensure_ascii=False)
                tool_calls.append({
                    "id": item.get("call_id") or item.get("id") or "tool",
                    "type": "function",
                    "function": {"name": item.get("name", ""), "arguments": arguments},
                })
        if not text_parts and isinstance(envelope.get("output_text"), str):
            text_parts.append(envelope["output_text"])
        if tool_calls:
            finish_reason = "tool_calls"
        elif refused:
            finish_reason = "content_filter"
        elif envelope.get("status") == "completed":
            finish_reason = "stop"
        elif envelope.get("status") == "incomplete":
            reason = (envelope.get("incomplete_details") or {}).get("reason")
            finish_reason = {"max_output_tokens": "length", "content_filter": "content_filter"}.get(reason, "unknown")
        else:
            finish_reason = "unknown"
        raw_usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
        normalized_usage = {}
        for source, target in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
                               ("total_tokens", "total_tokens")):
            value = raw_usage.get(source)
            if type(value) is int and value >= 0:
                normalized_usage[target] = value
        if "total_tokens" not in normalized_usage and all(
                key in normalized_usage for key in ("prompt_tokens", "completion_tokens")):
            normalized_usage["total_tokens"] = normalized_usage["prompt_tokens"] + normalized_usage["completion_tokens"]
        message = {"content": "".join(text_parts)}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return {"choices": [{"finish_reason": finish_reason, "message": message}], "usage": normalized_usage}
    if not is_anthropic(config):
        return envelope
    content = envelope.get("content") or []
    text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
    tool_calls = [{
        "id": block.get("id", "tool"),
        "type": "function",
        "function": {"name": block.get("name", ""), "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False)},
    } for block in content if block.get("type") == "tool_use"]
    stop_reason = envelope.get("stop_reason")
    finish_reason = {
        "end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length", "tool_use": "tool_calls",
    }.get(stop_reason, "unknown")
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    prompt = usage.get("input_tokens")
    completion = usage.get("output_tokens")
    normalized_usage = {}
    if type(prompt) is int and prompt >= 0:
        normalized_usage["prompt_tokens"] = prompt
    if type(completion) is int and completion >= 0:
        normalized_usage["completion_tokens"] = completion
    if "prompt_tokens" in normalized_usage and "completion_tokens" in normalized_usage:
        normalized_usage["total_tokens"] = prompt + completion
    message = {"content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"finish_reason": finish_reason, "message": message}], "usage": normalized_usage}
