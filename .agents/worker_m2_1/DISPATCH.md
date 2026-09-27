## 2026-09-26T14:18:24Z
You are worker_m2_1.
Your role: Core 2048 Engine & Math Domain Implementation Worker for Milestone 2.
Your working directory: e:\Learning\Python\agent_test\.agents\worker_m2_1
Authoritative user request: e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md
Scope document: e:\Learning\Python\agent_test\.agents\teamwork_preview_orchestrator_1\PROJECT.md
Target project directory: e:\Learning\Python\agent_test\android_2048_game

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
You have exclusive write ownership of all files inside:
`e:\Learning\Python\agent_test\android_2048_game\app\src\main\java\com\game2048\android\core\`
`e:\Learning\Python\agent_test\android_2048_game\app\src\test\java\com\game2048\android\core\`

Inputs to Read First:
1. e:\Learning\Python\agent_test\ORIGINAL_REQUEST.md
2. e:\Learning\Python\agent_test\.agents\teamwork_preview_orchestrator_1\PROJECT.md
3. e:\Learning\Python\agent_test\.agents\explorer_m2_1\handoff.md and grid_and_merge_plan.md
4. e:\Learning\Python\agent_test\.agents\explorer_m2_2\handoff.md and game_engine_plan.md
5. e:\Learning\Python\agent_test\.agents\explorer_m2_3\handoff.md and unit_test_plan.md

Implementation Tasks:
1. Implement Pure Kotlin Domain Data Models in `app/src/main/java/com/game2048/android/core/model/`:
   - `Position(val row: Int, val col: Int)`
   - `enum class MoveDirection { UP, DOWN, LEFT, RIGHT }`
   - `data class Tile(val id: Long, val value: Int, val isNew: Boolean = false, val mergedFrom: Pair<Long, Long>? = null)`
   - `class Grid(val rows: Int, val cols: Int)` supporting arbitrary dimensions (3x3, 4x4, 5x5), obstacle cells (`value = -1`), cell accessors, empty cell tracking, cloning/deep copy.
   - `data class TileMovement(val from: Position, val to: Position, val tileId: Long, val value: Int)`
   - `data class TileMerge(val sourceTileIds: Pair<Long, Long>, val resultingTile: Tile, val targetPosition: Position)`
   - `data class MoveResult(val moved: Boolean, val scoreGained: Int, val tileMovements: List<TileMovement>, val tileMerges: List<TileMerge>, val spawnedTile: Tile?, val isGameOver: Boolean, val isLevelWon: Boolean)`
   - `enum class GameState { IDLE, PLAYING, LEVEL_WON, GAME_OVER, PAUSED }`
   - `data class GameSaveState(val rows: Int, val cols: Int, val cells: List<List<Int>>, val score: Int, val highScore: Int, val state: GameState, val targetValue: Int, val levelId: Int)`

2. Implement Sliding & Game Engine in `app/src/main/java/com/game2048/android/core/engine/`:
   - `LineMerger.kt`: Deterministic 1D line compression and merge algorithm strictly enforcing the canonical single-pass non-double-merge invariant (`[2,2,4,4]->[4,8,0,0]`, `[2,2,2,0]->[4,2,0,0]`, `[4,2,2,0]->[4,4,0,0]`, `[2,0,2,4]->[4,4,0,0]`) and obstacle cell partitions (`-1`).
   - `RandomProvider.kt`: Interface and `DefaultRandomProvider` (using Kotlin `Random`, 90% 2 / 10% 4 distribution, random empty cell selection, seedable for tests).
   - `GameOverDetector.kt`: $O(RC)$ evaluation for empty cells and adjacent horizontal/vertical equal tiles.
   - `GameEngine.kt` interface and `GameEngineImpl.kt`:
     - Directional mapping for UP, DOWN, LEFT, RIGHT.
     - Spawns strictly ONE tile ONLY when `moved == true` (no-op blocked moves suppress spawn).
     - Score accumulation: strictly $\Delta S = \text{sum of merged tile values}$ ($2V$).
     - High score monotonic updating.
     - Reset protocol and state restore protocol.

3. Implement Exhaustive Pure JVM Domain Unit Tests in `app/src/test/java/com/game2048/android/core/`:
   - `LineMergerTest.kt`: All 16 truth table vectors from `spec_mechanics.md` Section 9, obstacle barriers, and cascade prevention.
   - `GridTest.kt`: Dimension variations (3x3, 4x4, 5x5), bounds checking, clone immutability, obstacle cells, and empty cell bookkeeping.
   - `GameEngineTest.kt`: Swipes in all 4 directions, score delta verification, blocked move spawn suppression, game-over trigger verification, and deterministic seeded replay.

4. Run Build & Test Pipeline:
   Run `.\gradlew.bat test` from `android_2048_game`:
   Ensure ALL unit tests pass with 100% pass rate.
   Run `.\gradlew.bat assembleRelease`:
   Ensure R8 compilation succeeds and release APK size remains strictly < 5 MB (~833 KB).

5. Document all code, test results, and outputs in:
   `e:\Learning\Python\agent_test\.agents\worker_m2_1\implementation_report.md`
6. Deliver a Hard Handoff report to:
   `e:\Learning\Python\agent_test\.agents\worker_m2_1\handoff.md`
   and notify the caller via send_message.
