"""Show observable events, never hidden reasoning or encrypted payloads."""
import json

ENABLED = True

def show(label, data):
    if ENABLED:
        print(f"\n[{label}]\n" + json.dumps(data, ensure_ascii=False, indent=2))

def show_response(response):
    visible = []
    for item in response.output:
        if item.type == "function_call":
            visible.append({"type": item.type, "name": item.name,
                            "call_id": item.call_id, "arguments": item.arguments})
        elif item.type == "message":
            visible.append({"type": item.type, "role": item.role,
                            "content": [part.model_dump(mode="json", exclude_none=True)
                                        for part in item.content]})
        else:
            visible.append({"type": item.type, "note": "仅显示类型，不展示内部推理或加密内容"})
    show("LLM 返回：真实 response.output", {"status": response.status, "output": visible})
