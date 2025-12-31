import json

def extract_json(text: str) -> dict:
    """
    Robustly extract JSON from LLM output.
    Supports:
    - pure JSON
    - ```json ... ```
    - ``` ... ```
    """
    text = text.strip()

    # Case 1: fenced code block
    if text.startswith("```"):
        lines = text.splitlines()
        # remove first ``` or ```json
        lines = lines[1:]
        # remove last ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return json.loads(text)