"""Offline scripted demonstration, not an LLM."""
import json

DEMO_TASKS = [
    "Read note.txt, remember its MEMORY_CODE, then delete note.txt. Do not repeat the code in your reply.",
    "Use the cd tool to enter archive. Create marker.txt containing ready. Reply briefly without repeating the remembered code.",
    "What was the MEMORY_CODE from the first task? Answer from your memory without using tools.",
]


class ScriptedClient:
    """Known tool plan, then a parser of visible history. Not an LLM or benchmark."""
    def __init__(self):
        self.index = 0
        self.plan = [("cat", {"path": "note.txt"}), ("rm", {"path": "note.txt"}), "Read and removed the note.",
                     ("cd", {"path": "archive"}), ("write_file", {"path": "marker.txt", "content": "ready\n"}),
                     "Created marker.txt."]

    def complete(self, messages, tools):
        index = self.index
        self.index += 1
        if index < len(self.plan):
            item = self.plan[index]
            if isinstance(item, str):
                return {"role": "assistant", "content": item}
            name, args = item
            return {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"call_{index}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}]}
        # No cached answer: the final response reads only messages provided by Memory.
        code = None
        for message in messages:
            if message["role"] == "tool":
                for line in json.loads(message["content"]).get("stdout", "").splitlines():
                    if line.startswith("MEMORY_CODE="):
                        code = line.partition("=")[2]
        return {"role": "assistant", "content": code or "Earlier observation is not available."}
