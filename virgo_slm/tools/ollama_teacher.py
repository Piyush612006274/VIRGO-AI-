"""Optional Qwen/Ollama teacher data generator for Virgo SLM distillation.

Ollama is a teacher only. Its outputs become training data; Virgo SLM remains the
student and the runtime never depends on Ollama once an artifact is exported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def ask(endpoint: str, model: str, prompt: str, timeout: int) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = Request(endpoint.rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = payload.get("response")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Ollama teacher returned no response")
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", required=True, type=Path, help="UTF-8 JSONL; each line contains {\"prompt\": ...}")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.prompts.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as target:
        for line_no, line in enumerate(source, 1):
            item = json.loads(line)
            prompt = item.get("prompt") if isinstance(item, dict) else None
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"Invalid prompt at line {line_no}")
            answer = ask(args.endpoint, args.model, prompt, args.timeout)
            target.write(json.dumps({"prompt": prompt, "response": answer}, ensure_ascii=False) + "\n")
    print(f"Teacher dataset written: {args.output}")
    print("Teacher: " + args.model)
    print("Student: Virgo SLM; Ollama is not required at inference time after export.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
