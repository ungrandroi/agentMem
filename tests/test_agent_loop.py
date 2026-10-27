"""Verify the shared loop without importing any experiment."""
import json
import unittest
from agent.loop import run_agent
from agent.memory import IdentityMemory


class AgentLoopTests(unittest.TestCase):
    def test_tool_feedback_and_private_state_boundary(self):
        state = {"private_marker": "evaluator-only", "value": 0}
        inputs = []

        class Client:
            def complete(self, messages, tools):
                inputs.append(messages)
                if len(inputs) == 1:
                    return {"role": "assistant", "tool_calls": [{
                        "id": "a", "type": "function",
                        "function": {"name": "increment", "arguments": "{}"}}]}
                return {"role": "assistant", "content": "Done"}

        def execute(call):
            state["value"] += 1
            return {"value": state["value"]}

        trace = run_agent(["Increment"], Client(), tools=[], execute_tool=execute,
                          system="Use tools", observe=lambda: state)
        self.assertEqual(trace["turns"][0]["status"], "completed")
        self.assertEqual(trace["steps"][0]["state_before"]["value"], 0)
        self.assertEqual(trace["steps"][0]["state_after"]["value"], 1)
        self.assertEqual(inputs[1][-1]["role"], "tool")
        self.assertEqual(json.loads(inputs[1][-1]["content"]), {"value": 1})
        self.assertNotIn("evaluator-only", json.dumps(inputs))

    def test_render_is_the_only_model_input(self):
        class Memory(IdentityMemory):
            def render(self):
                return [{"role": "user", "content": "controlled input"}]

        class Client:
            def complete(self, messages, tools):
                self.messages = messages
                return {"role": "assistant", "content": "Done"}

        client = Client()
        run_agent(["hidden task"], client, tools=[], execute_tool=lambda _: {},
                  system="hidden system", memory=Memory())
        self.assertEqual(client.messages, [{"role": "user", "content": "controlled input"}])
