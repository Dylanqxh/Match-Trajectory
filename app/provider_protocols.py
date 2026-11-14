"""Small protocol boundary for OpenAI-compatible and Anthropic-native APIs."""
import json


def is_anthropic(config) -> bool:
    return config.provider == "anthropic"


def request_endpoint(config) -> str:
    suffix = "/messages" if is_anthropic(config) else "/chat/completions"
    return config.base_url if config.base_url.endswith(suffix) else config.base_url + suffix


def request_headers(config) -> dict[str, str]:
    secret = config.api_key.get_secret_value()
    if is_anthropic(config):
        return {"x-api-key": secret, "anthropic-version": "2023-06-01"}
    return {"Authorization": "Bearer " + secret}


def adapt_request(config, payload: dict) -> dict:
    """Convert the application's OpenAI-shaped request to the selected wire format."""
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
