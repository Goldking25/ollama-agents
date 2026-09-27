# Milestone 2 Technical Handoff Report: Grid Representation & 1D/2D Slide-and-Merge Engine

**Agent:** `explorer_m2_1`  
**Role:** Grid Representation & 1D/2D Slide-and-Merge Algorithm Explorer  
**Working Directory:** `e:\Learning\Python\agent_test\.agents\explorer_m2_1`  
**Target Milestone:** Milestone 2 (Core 2048 Engine & Math Domain)  
**Status:** Completed (Hard Handoff)  
**Primary Deliverable Plan:** `e:\Learning\Python\agent_test\.agents\explorer_m2_1\grid_and_merge_plan.md`  

---

## 1. Observation

1. **Authoritative Requirements (`ORIGINAL_REQUEST.md`)**:
   - `ORIGINAL_REQUEST.md:12`: "### R1. Core 2048 Gameplay & Fluid Animations: Deliver complete 2048 game mechanics including swipe gesture detection in all 4 cardinal directions, score tracking, high-score persistence, board reset, and game-over detection. Provide fluid visual animations for tile sliding, merging (scale pop), and new tile appearances..."
   - `ORIGINAL_REQUEST.md:15`: "### R2. Progressive Level System: Implement an escalating level progression system... (e.g. escalating target numbers, adjusted board dimensions, or special grid layouts)."
   - `ORIGINAL_REQUEST.md:24`: "Grid sliding logic passes automated test suites verifying correct tile movements, merges, edge collision, score accumulation, and game-over detection."

2. **Project Scope & Architecture (`PROJECT.md`)**:
   - `PROJECT.md:16`: "F02: Deterministic Grid Representation — 2D/1D grid model supporting arbitrary dimensions (3x3, 4x4, 5x5) and obstacles (-1) | M2"
   - `PROJECT.md:17`: "F03: 1D/2D Slide & Merge Algorithm — Canonical single-pass non-double-merge invariant (`[2,2,4,4]->[4,8,0,0]`, `[2,2,2,0]->[4,2,0,0]`) | M2"
   - `PROJECT.md:18`: "F04: Score Accumulation Engine — Real-time score computation ($\Delta S = \text{sum of merged tile values}$) | M2"
   - `PROJECT.md:19`: "F05: Deterministic Tile Spawning — Bernoulli 90%/10% (2 vs 4), empty cell selection, seedable PRNG interface, spawns only on move | M2"
   - `PROJECT.md:20`: "F06: Game-Over Detection — $O(RC)$ evaluation for zero empty cells and no adjacent horizontal/vertical equal tiles | M2"

3. **Mechanics Specification (`spec_mechanics.md`)**:
   - `spec_mechanics.md:46`: Tile data model: `id: Long`, `value: Int`, `row: Int`, `col: Int`.
   - `spec_mechanics.md:68-73`: Cardinal direction mappings: LEFT (rows left-to-right), RIGHT (rows right-to-left), UP (cols top-to-bottom), DOWN (cols bottom-to-top).
   - `spec_mechanics.md:79-126`: Formal 1D algorithm: `compressAndMergeLine(line: List<Tile?>): LineResult`.
   - `spec_mechanics.md:134-145`: Merge Truth Table (`[2,2,4,4]->[4,8,0,0]`, `[2,2,2,0]->[4,2,0,0]`, `[2,2,2,2]->[4,4,0,0]`, `[4,2,2,0]->[4,4,0,0]`, etc.).
   - `spec_mechanics.md:173-177`: Obstacle partition rule: `[2, 2, -1, 4, 4]` sliding LEFT $\to$ `[4, 0, -1, 8, 0]`. Obstacle stays at index 2, separates merge domains.
   - `spec_mechanics.md:273-300`: Fast $O(RC)$ game over check.

4. **Target Project State (`android_2048_game`)**:
   - `app/build.gradle.kts:65-67`: Pure JVM testing dependency `testImplementation("junit:junit:4.13.2")` is pre-configured and fully functional.
   - `app/src/test/java/com/game2048/android/SmokeUnitTest.kt`: Baseline smoke test passing on JVM.
   - No models or engine files exist yet in `app/src/main/java/com/game2048/android/core`.

---

## 2. Logic Chain

1. **Decoupled Architecture Rationale**:
   - As observed in `app/build.gradle.kts:65`, pure JVM unit testing via JUnit 4 runs without Android emulator or instrumentation overhead (< 1 second execution).
   - Therefore, all data models (`Position`, `MoveDirection`, `Tile`, `Grid`, `TileMovement`, `TileMerge`, `MoveResult`) and engines (`LineMerger`, `GridEngine`, `RandomProvider`, `TileIdGenerator`) must reside in pure Kotlin packages with zero imports from `android.*`.

2. **1D Canonical Invariant & Obstacle Partitioning**:
   - By mapping every 2D swipe (UP, DOWN, LEFT, RIGHT) to 1D lines whose index 0 corresponds to the destination boundary (Obs 3, `spec_mechanics.md:68-73`), all sliding and merging logic collapses into a single deterministic 1D function: `LineMerger.compressAndMergeLine`.
   - Obstacles (`value = -1`) are immovable boundaries. By splitting each line into segments between obstacle indices, each sub-segment $[start..end]$ can be compressed independently towards $start$, preserving obstacle positions and preventing illegal merges across walls (Obs 3, `spec_mechanics.md:173-177`).
   - Within each subsegment, a two-pointer pass evaluates adjacent non-empty tile pairs: if $T_i.\text{value} == T_{i+1}.\text{value}$, a merge occurs into $2 \times \text{value}$, generating a new unique `Tile`, advancing the pointer by $+2$, strictly preventing secondary merges within the same turn (Obs 3, `spec_mechanics.md:134-145`).

3. **Animation Support Contract**:
   - Milestone 4 mandates fluid 60+ FPS two-phase animations: 120ms slide translation followed by 100ms merge-pop / spawn-in (Obs 1, `ORIGINAL_REQUEST.md:13`).
   - To drive this without runtime inspection or allocation in the UI view, `MoveResult` emits immutable lists of `TileMovement(from, to, tileId, value)` and `TileMerge(sourceTileIds, resultingTile, targetPosition)`. Every moved tile (including those sliding into collision) is tracked.

4. **Game-Over & Board Legality Soundness**:
   - On full boards ($0$ empty cells), a swipe is possible if and only if adjacent equal tiles exist horizontally or vertically.
   - With obstacle partitions, cells walled off by obstacles cannot participate in moves. The function `canMove(direction: MoveDirection)` verifies in $O(RC)$ whether any tile has an in-bounds adjacent cell in that direction that is either empty ($0$) or equal in value.
   - `isGameOver()` is true if and only if `canMove(d)` is false for all $d \in \{\text{UP}, \text{DOWN}, \text{LEFT}, \text{RIGHT}\}$.

---

## 3. Caveats

- **Scope Boundary**: This handoff covers pure domain data models and 1D/2D sliding algorithms for Milestone 2. Level catalog configurations, star rating calculations, and persistent JSON storage belong to Milestone 3. Canvas rendering and `ValueAnimator` pipelines belong to Milestone 4.
- **Assumptions**: The grid dimensions are assumed to be bounded by $R, C \in [2, 8]$ (supporting 3x3, 4x4, 5x5). Values outside this range throw `IllegalArgumentException`.
- **Alternative Interpretations Considered**: Considered having `compressAndMergeLine` operate purely on 1D integers `IntArray`. Rejected as insufficient because the animation pipeline in Milestone 4 requires persistent `Tile.id` tracking and exact 2D `from` $\to$ `to` coordinate vectors. We solved this elegantly by providing both: `compressAndMergeLine` with full 2D position projections, plus a lightweight `compressAndMergeValues` helper for mathematical assertions.

---

## 4. Conclusion

The specification plan in `e:\Learning\Python\agent_test\.agents\explorer_m2_1\grid_and_merge_plan.md` provides complete, unambiguous, drop-in Kotlin code for:
1. `com.game2048.android.core.model`:
   - `Position(val row: Int, val col: Int)`
   - `enum class MoveDirection { UP, DOWN, LEFT, RIGHT }`
   - `data class Tile(val id: Long, val value: Int, val position: Position)`
   - `class Grid(val rows: Int, val cols: Int, initialObstacles: Set<Position> = emptySet())`
   - `data class TileMovement(val from: Position, val to: Position, val tileId: Long, val value: Int)`
   - `data class TileMerge(val sourceTileIds: Pair<Long, Long>, val resultingTile: Tile, val targetPosition: Position)`
   - `data class MoveResult(val moved: Boolean, val scoreGained: Int, val tileMovements: List<TileMovement>, val tileMerges: List<TileMerge>, val spawnedTile: Tile?, val isGameOver: Boolean, val isLevelWon: Boolean)`
2. `com.game2048.android.core.engine`:
   - `LineMerger.compressAndMergeLine`: Deterministic single-pass merge algorithm with obstacle partitioning.
   - `GridEngine`: 2D directional swipe orchestrator, score accumulator, tile spawner, game-over & win evaluator.
   - `RandomProvider`: Injectable randomness interface (`DefaultRandomProvider`, `SeededRandomProvider`, `DeterministicRandomProvider`).
   - `TileIdGenerator`: Thread-safe monotonic ID generator (`AtomicTileIdGenerator`).
3. Complete JUnit 4 Unit Test Suites:
   - `LineMergerTest.kt`: 21 test methods covering all canonical truth tables, edge cases, and obstacle interactions.
   - `GridModelTest.kt`: 6 test methods covering 3x3, 4x4, 5x5 dimensions, bounds validation, obstacle immutability, and deep copy.
   - `GridEngineTest.kt`: 8 test methods covering 4-direction swipes, mutation guards, score accumulation, game over detection, and level win conditions.

---

## 5. Verification Method

The implementer agent can independently verify this plan by executing the following steps:

1. **Inspect Plan File**:
   Read `e:\Learning\Python\agent_test\.agents\explorer_m2_1\grid_and_merge_plan.md`.
2. **Apply Code to Project**:
   Create the model and engine files in `android_2048_game/app/src/main/java/com/game2048/android/core/` and the unit test files in `android_2048_game/app/src/test/java/com/game2048/android/core/`.
3. **Run Unit Tests**:
   Execute the Gradle unit test task in powershell:
   ```powershell
   cd e:\Learning\Python\agent_test\android_2048_game
   .\gradlew.bat testDebugUnitTest --info
   ```
4. **Invalidation Conditions**:
   - Any failure of canonical merge cases (e.g. `[2,2,2,0]` resulting in anything other than `[4,2,0,0]`, or `[2,2,4,4]` not producing `[4,8,0,0]`).
   - Any tile crossing an obstacle boundary (`value = -1`).
   - Any dependency on `android.*` packages within `core.model` or `core.engine`.
   - Any test failure in `LineMergerTest`, `GridModelTest`, or `GridEngineTest`.
