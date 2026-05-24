import asyncio
import unittest

from app.agent.nodes.merge_retrieved_info import merge_retrieved_info


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {"meta_mysql_repository": object()}

    def stream_writer(self, event):
        self.events.append(event)


class MergeRetrievedInfoDynamicRouteTest(unittest.TestCase):
    def test_merge_retrieved_info_allows_skipped_recall_branches(self):
        runtime = FakeRuntime()
        state = {
            "agent_plan": {
                "tool_calls": [
                    {
                        "id": "tool_1",
                        "name": "recall_metric",
                        "args": {"hints": ["GMV"]},
                        "reason": "需要指标召回",
                    }
                ],
            },
        }

        result = asyncio.run(merge_retrieved_info(state, runtime))

        self.assertEqual(result["table_infos"], [])
        self.assertEqual(result["metric_infos"], [])
        self.assertEqual(runtime.events[-1]["type"], "trace")
        self.assertEqual(runtime.events[-1]["step"], "合并召回信息")


if __name__ == "__main__":
    unittest.main()
