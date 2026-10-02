import unittest
from unittest.mock import MagicMock, patch

from ollama_agents.goal import GoalRegistry, GoalTask, is_task_failure_output
from ollama_agents.planner import Planner


class TestDynamicReplanningAndCascading(unittest.TestCase):
    def setUp(self):
        self.registry = GoalRegistry()
        self.goal_id = "test-replan-goal-001"
        if self.registry.exists(self.goal_id):
            self.registry.delete_goal(self.goal_id)

    def tearDown(self):
        if self.registry.exists(self.goal_id):
            self.registry.delete_goal(self.goal_id)

    def test_01_is_task_failure_output_detection(self):
        self.assertTrue(is_task_failure_output("[Error] File not found"))
        self.assertTrue(is_task_failure_output("[Tool Failure] Command failed"))
        self.assertTrue(is_task_failure_output("Agent stopped: repeated identical tool call"))
        self.assertTrue(is_task_failure_output("Task timed out after turn limit."))
        self.assertTrue(is_task_failure_output("Traceback (most recent call last):"))
        self.assertFalse(is_task_failure_output("Task completed successfully. Final Answer: here is the data."))

    def test_02_replan_remaining_tasks(self):
        # Create a goal with 3 initial tasks
        goal = self.registry.create(
            description="Build automated data scraper",
            task_descriptions=[
                "Task 1: Setup project directory",
                "Task 2: Download raw HTML via curl",
                "Task 3: Parse HTML into CSV",
            ],
            agent_name="TestAgent",
            goal_id=self.goal_id,
        )
        self.assertEqual(len(goal.tasks), 3)

        # Complete task 1
        self.registry.complete_task(self.goal_id, "task-001", output="Directory created")

        # Mark task 2 as failed
        self.registry.fail_task(self.goal_id, "task-002", reason="curl failed: 403 Forbidden")

        # Replanner provides 2 new steps to bypass the 403 error
        revised_steps = [
            "Task 2-alt: Use Playwright with browser headers to fetch content",
            "Task 3-alt: Parse rendered DOM into CSV",
        ]
        success = self.registry.replan_remaining_tasks(self.goal_id, "task-002", revised_steps)
        self.assertTrue(success)

        # Reload goal
        updated_goal = self.registry.load(self.goal_id)
        self.assertIsNotNone(updated_goal)
        # Should have: task-001 (completed), task-002 (failed), and 2 newly planned tasks
        self.assertEqual(len(updated_goal.tasks), 4)
        self.assertEqual(updated_goal.tasks[0].id, "task-001")
        self.assertEqual(updated_goal.tasks[0].status, "completed")
        self.assertEqual(updated_goal.tasks[1].id, "task-002")
        self.assertEqual(updated_goal.tasks[1].status, "failed")
        self.assertEqual(updated_goal.tasks[2].description, revised_steps[0])
        self.assertEqual(updated_goal.tasks[2].status, "pending")
        self.assertEqual(updated_goal.tasks[3].description, revised_steps[1])
        self.assertEqual(updated_goal.tasks[3].status, "pending")

        # Next task should be the first revised task
        next_t = updated_goal.next_task
        self.assertIsNotNone(next_t)
        self.assertEqual(next_t.description, revised_steps[0])

    def test_03_block_downstream_tasks_cascading(self):
        # Create a goal with 3 tasks
        goal = self.registry.create(
            description="Compile Android app",
            task_descriptions=[
                "Task 1: Generate Java code",
                "Task 2: Compile classes.dex",
                "Task 3: Package APK with apkbuilder",
            ],
            agent_name="TestAgent",
            goal_id=self.goal_id,
        )

        # Task 1 failed and no alternative path exists
        self.registry.fail_task(self.goal_id, "task-001", reason="Syntax errors in generated Java code")
        self.registry.block_downstream_tasks(
            self.goal_id,
            "task-001",
            reason="Cannot compile without source code",
        )

        updated_goal = self.registry.load(self.goal_id)
        self.assertIsNotNone(updated_goal)
        self.assertEqual(updated_goal.status, "blocked")
        self.assertEqual(updated_goal.tasks[0].status, "failed")
        self.assertEqual(updated_goal.tasks[1].status, "blocked")
        self.assertEqual(updated_goal.tasks[2].status, "blocked")
        self.assertIn("Cascaded Block", updated_goal.tasks[1].output)
        self.assertIn("Cascaded Block", updated_goal.tasks[2].output)

        # Because goal is blocked, next_task should be None (no execution allowed)
        self.assertIsNone(updated_goal.next_task)


if __name__ == "__main__":
    unittest.main()
