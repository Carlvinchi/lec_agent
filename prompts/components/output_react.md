## Output Format

Respond with **exactly one** of these JSON objects — no markdown fences:

Tool call:
```
{"thought": "...", "action": "<tool_name>", "action_input": {...}}
```

Final answer (only when you have sufficient evidence):
```
{"thought": "...", "final_answer": "<answer with specific numbers and source citations>"}
```
