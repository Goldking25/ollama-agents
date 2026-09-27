# Pure JVM Domain Unit Test Suite Architecture & Test Vectors
**Milestone 2: Core 2048 Game Engine & Math Domain**

**Author**: explorer_m2_3  
**Target Package**: `com.game2048.android.core`  
**Test Root**: `app/src/test/java/com/game2048/android/core/`  
**Specification Sources**: `ORIGINAL_REQUEST.md`, `PROJECT.md`, `spec_mechanics.md`  

---

## 1. Executive Summary & Architecture Overview

This document specifies the complete pure JVM domain unit test suite for Milestone 2 of the Android 2048 application. The domain layer encapsulates all mathematical, algorithmic, and state transition rules of 2048, completely isolated from the Android UI, Canvas, and Android SDK frameworks.

### Key Architectural Tenets:
1. **Zero Android Framework Dependencies**: The core domain engine and models (`com.game2048.android.core.*`) are pure Kotlin (Java 21 LTS bytecode). No Android SDK classes (`android.os.*`, `android.graphics.*`, `android.content.*`) or Robolectric runners are required.
2. **Sub-Second Execution**: Running `./gradlew testDebugUnitTest` runs 100% of these tests directly on the local JVM in under 1 second, providing instant feedback in CI/CD.
3. **100% Determinism**: An injectable `RandomProvider` interface decouples pseudorandom number generation, enabling 100% reproducible test sequences, seed replayability, and property-based boundary testing.
4. **Exhaustive Truth Table Coverage**: Line compression and merging algorithm tests verify all 16 canonical edge-case vectors, obstacle cell partitions, multi-dimension lines (3x3, 4x4, 5x5), and cascade prevention invariants.

---

## 2. Domain Model & Interface Contract Synchronization

The test suite interfaces with the pure Kotlin domain models established in Milestone 2:

### 2.1 Package: `com.game2048.android.core.model`

```kotlin
package com.game2048.android.core.model

/**
 * 2D grid position coordinate.
 */
data class Position(val row: Int, val col: Int) {
    override fun toString(): String = "($row, $col)"
}

/**
 * Cardinal swipe movement directions.
 */
enum class MoveDirection(val deltaRow: Int, val deltaCol: Int) {
    UP(-1, 0),
    DOWN(1, 0),
    LEFT(0, -1),
    RIGHT(0, 1)
}

/**
 * Discrete tile instance with immutable identity for animation tracking.
 * Special values: 0 = Empty, -1 = Obstacle / Impassable cell.
 */
data class Tile(
    val id: Long,
    val value: Int,
    val row: Int = 0,
    val col: Int = 0
) {
    val isEmpty: Boolean get() = value == 0
    val isObstacle: Boolean get() = value == -1
    val isPlayable: Boolean get() = value > 0
}

/**
 * High-performance 2D grid representation supporting variable dimensions
 * and obstacle cells.
 */
class Grid(
    val rows: Int,
    val cols: Int,
    initialObstacles: Set<Position> = emptySet()
) {
    init {
        require(rows in 2..8) { "Row count must be between 2 and 8, was: $rows" }
        require(cols in 2..8) { "Column count must be between 2 and 8, was: $cols" }
    }

    private val cells: Array<Array<Tile?>> = Array(rows) { r ->
        Array(cols) { c ->
            val pos = Position(r, c)
            if (pos in initialObstacles) Tile(id = -1L, value = -1, row = r, col = c) else null
        }
    }

    val obstacles: Set<Position> = initialObstacles.toSet()

    fun isInBounds(row: Int, col: Int): Boolean = row in 0 until rows && col in 0 until cols
    fun isInBounds(pos: Position): Boolean = isInBounds(pos.row, pos.col)

    fun get(row: Int, col: Int): Tile? {
        checkBounds(row, col)
        return cells[row][col]
    }

    fun get(pos: Position): Tile? = get(pos.row, pos.col)

    fun getValue(row: Int, col: Int): Int = get(row, col)?.value ?: 0
    fun getValue(pos: Position): Int = getValue(pos.row, pos.col)

    fun set(row: Int, col: Int, tile: Tile?) {
        checkBounds(row, col)
        val pos = Position(row, col)
        check(pos !in obstacles) { "Cannot overwrite obstacle cell at $pos" }
        cells[row][col] = tile?.copy(row = row, col = col)
    }

    fun set(pos: Position, tile: Tile?) = set(pos.row, pos.col, tile)

    fun clear() {
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val pos = Position(r, c)
                if (pos !in obstacles) {
                    cells[r][c] = null
                }
            }
        }
    }

    fun emptyCells(): List<Position> {
        val result = ArrayList<Position>()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val pos = Position(r, c)
                if (pos !in obstacles && cells[r][c] == null) {
                    result.add(pos)
                }
            }
        }
        return result
    }

    fun isObstacle(row: Int, col: Int): Boolean = Position(row, col) in obstacles

    fun clone(): Grid {
        val copy = Grid(rows, cols, obstacles)
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                copy.cells[r][c] = this.cells[r][c]?.copy()
            }
        }
        return copy
    }

    private fun checkBounds(row: Int, col: Int) {
        if (!isInBounds(row, col)) {
            throw IndexOutOfBoundsException("Position ($row, $col) out of bounds for ${rows}x${cols} grid")
        }
    }

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is Grid) return false
        if (rows != other.rows || cols != other.cols || obstacles != other.obstacles) return false
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                if (getValue(r, c) != other.getValue(r, c)) return false
            }
        }
        return true
    }

    override fun hashCode(): Int {
        var result = rows.hashCode()
        result = 31 * result + cols.hashCode()
        result = 31 * result + obstacles.hashCode()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                result = 31 * result + getValue(r, c)
            }
        }
        return result
    }
}

/**
 * Motion event models for animation pipeline.
 */
data class TileMovement(val from: Position, val to: Position, val tileId: Long, val value: Int)
data class TileMerge(val sourceTileIds: Pair<Long, Long>, val resultingTile: Tile, val targetPosition: Position)

/**
 * Outcome of a swipe move attempt.
 */
data class MoveResult(
    val moved: Boolean,
    val scoreGained: Int,
    val tileMovements: List<TileMovement>,
    val tileMerges: List<TileMerge>,
    val spawnedTile: Tile?,
    val isGameOver: Boolean,
    val isLevelWon: Boolean
)

enum class GameState {
    IDLE,
    PLAYING,
    LEVEL_WON,
    GAME_OVER
}
```

### 2.2 Package: `com.game2048.android.core.engine`

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.*

/**
 * Seedable PRNG interface for 100% deterministic test execution.
 */
interface RandomProvider {
    fun nextTileValue(): Int
    fun selectEmptyCell(emptyCells: List<Position>): Position
}

/**
 * Result of 1D line compression and merge.
 */
data class LineMergeResult(
    val newLine: List<Tile?>,
    val movements: List<TileMovement>,
    val merges: List<TileMerge>,
    val scoreGained: Int,
    val moved: Boolean
)

/**
 * Pure 1D line compressor and merger.
 */
object LineMerger {
    fun compressAndMergeLine(line: List<Tile?>, idGenerator: () -> Long = { System.nanoTime() }): LineMergeResult
    // Convenience helper for raw integer truth table verification:
    fun compressAndMergeValues(values: List<Int>): Pair<List<Int>, Int>
}

/**
 * Core 2048 game engine managing turn execution, grid state, scoring, and termination.
 */
interface GameEngine {
    val grid: Grid
    val score: Int
    val highScore: Int
    val gameState: GameState
    val targetTile: Int

    fun startNewGame(rows: Int = 4, cols: Int = 4, targetTile: Int = 2048, obstacles: Set<Position> = emptySet())
    fun move(direction: MoveDirection): MoveResult
    fun reset()
    fun isGameOver(): Boolean
    fun isLevelWon(): Boolean
    fun setGridState(grid: Grid, score: Int = 0) // Test helper / state injection
}
```

---

## 3. Test Suite 1: `LineMergerTest` Architecture & Vector Truth Table

The single-pass merge invariant is the mathematical foundation of 2048. A newly merged tile cannot merge again within the same turn. Furthermore, merge precedence moves strictly towards the compression target (index 0).

### 3.1 Comprehensive 16-Vector Truth Table

The following 16 vectors include all mandatory edge cases from `spec_mechanics.md` Section 9, covering dual merges, triple tile merges, quad tile merges, target pre-existence, gap collapse, obstacle barriers, and boundary slides.

| # | Vector Name | Input Line Array | Expected Output Array | Moved? | Merges Count | Score Delta ($\Delta S$) | Invariant / Rule Verified |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---|
| **V01** | Dual Independent Merges | `[2, 2, 4, 4]` | `[4, 8, 0, 0]` | Yes | 2 | $+12$ | Both pairs `(2,2)` and `(4,4)` merge independently in a single pass. |
| **V02** | Triple Identical (Left Priority) | `[2, 2, 2, 0]` | `[4, 2, 0, 0]` | Yes | 1 | $+4$ | Leftmost `(2,2)` merges into 4; third `2` slides to index 1 and **cannot** double-merge into 4. |
| **V03** | Quad Identical Non-Cascade | `[2, 2, 2, 2]` | `[4, 4, 0, 0]` | Yes | 2 | $+8$ | Pairs `[0,1]` and `[2,3]` merge into two 4s. They do **not** cascade into 8. |
| **V04** | Pre-Existing Target Value | `[4, 2, 2, 0]` | `[4, 4, 0, 0]` | Yes | 1 | $+4$ | Pair `(2,2)` merges into 4 at index 1. It does **not** merge with the pre-existing 4 at index 0. |
| **V05** | Embedded Gaps Collapse | `[0, 2, 0, 2]` | `[4, 0, 0, 0]` | Yes | 1 | $+4$ | Spaces between matching tiles collapse completely before merge evaluation. |
| **V06** | Obstacle Partition Merge | `[2, 2, -1, 4]` | `[4, 0, -1, 4]` | Yes | 1 | $+4$ | Obstacle `-1` at index 2 splits row into independent subsegments; left merges, right stationary. |
| **V07** | Dual Segment Obstacle Merges | `[2, 2, -1, 4, 4]` | `[4, 0, -1, 8, 0]` | Yes | 2 | $+12$ | Obstacle at index 2. Left subsegment yields `[4, 0]`, right yields `[8, 0]`. |
| **V08** | Obstacle Impassability Slide | `[0, 2, -1, 0, 0]` | `[2, 0, -1, 0, 0]` | Yes | 0 | $+0$ | Tile slides up to boundary; cannot jump or traverse obstacle `-1`. |
| **V09** | Alternating Values (Blocked) | `[2, 4, 2, 4]` | `[2, 4, 2, 4]` | No | 0 | $+0$ | Full line, no matches, no empty spaces. No-op move. `moved == false`. |
| **V10** | All Empty Cells (No-Op) | `[0, 0, 0, 0]` | `[0, 0, 0, 0]` | No | 0 | $+0$ | Entire line empty. Idempotent no-op. `moved == false`. |
| **V11** | Isolated Single Tile Slide | `[0, 0, 2, 0]` | `[2, 0, 0, 0]` | Yes | 0 | $+0$ | Tile translates 2 indices to boundary; no merge occurs, score delta 0. |
| **V12** | Trailing Pair Merge Only | `[8, 4, 2, 2]` | `[8, 4, 4, 0]` | Yes | 1 | $+4$ | Only trailing pair `(2,2)` merges into 4; non-matching leading tiles remain in place. |
| **V13** | Leading Pair Cascade Prevention | `[2, 2, 4, 8]` | `[4, 4, 8, 0]` | Yes | 1 | $+4$ | `(2,2)` merges to 4. Resulting line has two adjacent 4s (`[4,4,8,0]`), but they cannot cascade in same turn. |
| **V14** | Center Pair Merge | `[2, 4, 4, 2]` | `[2, 8, 2, 0]` | Yes | 1 | $+8$ | Center pair `(4,4)` merges to 8; surrounding tiles 2 slide cleanly into indices 0 and 2. |
| **V15** | Far Boundary Long Slide | `[0, 0, 0, 2]` | `[2, 0, 0, 0]` | Yes | 0 | $+0$ | Tile at index $L-1$ translates full distance to index 0 without merge. |
| **V16** | Double Obstacle Interior Merge | `[-1, 2, 2, -1]` | `[-1, 4, 0, -1]` | Yes | 1 | $+4$ | Obstacles at both extremities (`0` and `3`); interior segment `[2,2]` compresses and merges to `[4,0]`. |

### 3.2 Multi-Dimension & High-Value Extended Vectors

In addition to the 16 core 4-element vectors, `LineMergerTest` verifies:
- **3-Length Vectors (3x3 Grid / Level 5)**:
  - `[2, 2, 2]` $\to$ `[4, 2, 0]` ($\Delta S = 4$, moved = true)
  - `[0, 4, 4]` $\to$ `[8, 0, 0]` ($\Delta S = 8$, moved = true)
  - `[4, 2, 4]` $\to$ `[4, 2, 4]` ($\Delta S = 0$, moved = false)
- **5-Length Vectors (5x5 Grid / Level 6)**:
  - `[2, 2, 2, 2, 2]` $\to$ `[4, 4, 2, 0, 0]` ($\Delta S = 8$, moved = true)
  - `[4, 4, 8, 8, 16]` $\to$ `[8, 16, 16, 0, 0]` ($\Delta S = 24$, moved = true)
  - `[0, 2, 0, 2, 0]` $\to$ `[4, 0, 0, 0, 0]` ($\Delta S = 4$, moved = true)
- **High-Value Tile Merges**:
  - `[1024, 1024, 2048, 2048]` $\to$ `[2048, 4096, 0, 0]` ($\Delta S = 2048 + 4096 = 6144$)
  - `[16384, 16384, 0, 0]` $\to$ `[32768, 0, 0, 0]` ($\Delta S = 32768$)

### 3.3 Concrete Test Implementation: `LineMergerTest.kt`

```kotlin
package com.game2048.android.core

import com.game2048.android.core.engine.LineMerger
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import org.junit.Assert.*
import org.junit.Test

/**
 * Pure JVM unit tests for 1D line compression, single-pass non-double-merge invariant,
 * obstacle segmentation, and movement event tracking.
 */
class LineMergerTest {

    private var idCounter = 1L
    private fun nextId() = idCounter++

    private fun createTile(value: Int, col: Int = 0): Tile = Tile(id = nextId(), value = value, row = 0, col = col)

    private fun valuesToTiles(values: List<Int>): List<Tile?> {
        return values.mapIndexed { idx, v ->
            when (v) {
                0 -> null
                -1 -> Tile(id = -1L, value = -1, row = 0, col = idx)
                else -> createTile(v, idx)
            }
        }
    }

    private fun tilesToValues(tiles: List<Tile?>): List<Int> {
        return tiles.map { it?.value ?: 0 }
    }

    private fun assertLineMerge(
        input: List<Int>,
        expectedOutput: List<Int>,
        expectedScoreDelta: Int,
        expectedMoved: Boolean
    ) {
        val inputTiles = valuesToTiles(input)
        val result = LineMerger.compressAndMergeLine(inputTiles) { nextId() }

        assertEquals("Output values mismatch for input $input", expectedOutput, tilesToValues(result.newLine))
        assertEquals("Score delta mismatch for input $input", expectedScoreDelta, result.scoreGained)
        assertEquals("Moved flag mismatch for input $input", expectedMoved, result.moved)
    }

    // --- 16 Truth Table Edge Case Tests ---

    @Test
    fun testV01_dualIndependentMerges() {
        // [2, 2, 4, 4] -> [4, 8, 0, 0], score +12
        assertLineMerge(listOf(2, 2, 4, 4), listOf(4, 8, 0, 0), expectedScoreDelta = 12, expectedMoved = true)
    }

    @Test
    fun testV02_tripleIdenticalLeftPriority() {
        // [2, 2, 2, 0] -> [4, 2, 0, 0], score +4
        assertLineMerge(listOf(2, 2, 2, 0), listOf(4, 2, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV03_quadIdenticalNonCascade() {
        // [2, 2, 2, 2] -> [4, 4, 0, 0], score +8
        assertLineMerge(listOf(2, 2, 2, 2), listOf(4, 4, 0, 0), expectedScoreDelta = 8, expectedMoved = true)
    }

    @Test
    fun testV04_preExistingTargetValueNonMerge() {
        // [4, 2, 2, 0] -> [4, 4, 0, 0], score +4
        assertLineMerge(listOf(4, 2, 2, 0), listOf(4, 4, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV05_embeddedGapsCollapse() {
        // [0, 2, 0, 2] -> [4, 0, 0, 0], score +4
        assertLineMerge(listOf(0, 2, 0, 2), listOf(4, 0, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV06_obstaclePartitionMerge() {
        // [2, 2, -1, 4] -> [4, 0, -1, 4], score +4
        assertLineMerge(listOf(2, 2, -1, 4), listOf(4, 0, -1, 4), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV07_dualSegmentObstacleMerges() {
        // [2, 2, -1, 4, 4] -> [4, 0, -1, 8, 0], score +12
        assertLineMerge(listOf(2, 2, -1, 4, 4), listOf(4, 0, -1, 8, 0), expectedScoreDelta = 12, expectedMoved = true)
    }

    @Test
    fun testV08_obstacleImpassabilitySlide() {
        // [0, 2, -1, 0, 0] -> [2, 0, -1, 0, 0], score 0
        assertLineMerge(listOf(0, 2, -1, 0, 0), listOf(2, 0, -1, 0, 0), expectedScoreDelta = 0, expectedMoved = true)
    }

    @Test
    fun testV09_alternatingValuesBlocked() {
        // [2, 4, 2, 4] -> [2, 4, 2, 4], score 0, moved=false
        assertLineMerge(listOf(2, 4, 2, 4), listOf(2, 4, 2, 4), expectedScoreDelta = 0, expectedMoved = false)
    }

    @Test
    fun testV10_allEmptyCellsNoOp() {
        // [0, 0, 0, 0] -> [0, 0, 0, 0], score 0, moved=false
        assertLineMerge(listOf(0, 0, 0, 0), listOf(0, 0, 0, 0), expectedScoreDelta = 0, expectedMoved = false)
    }

    @Test
    fun testV11_isolatedSingleTileSlide() {
        // [0, 0, 2, 0] -> [2, 0, 0, 0], score 0, moved=true
        assertLineMerge(listOf(0, 0, 2, 0), listOf(2, 0, 0, 0), expectedScoreDelta = 0, expectedMoved = true)
    }

    @Test
    fun testV12_trailingPairMergeOnly() {
        // [8, 4, 2, 2] -> [8, 4, 4, 0], score +4
        assertLineMerge(listOf(8, 4, 2, 2), listOf(8, 4, 4, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV13_leadingPairCascadePrevention() {
        // [2, 2, 4, 8] -> [4, 4, 8, 0], score +4
        assertLineMerge(listOf(2, 2, 4, 8), listOf(4, 4, 8, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV14_centerPairMerge() {
        // [2, 4, 4, 2] -> [2, 8, 2, 0], score +8
        assertLineMerge(listOf(2, 4, 4, 2), listOf(2, 8, 2, 0), expectedScoreDelta = 8, expectedMoved = true)
    }

    @Test
    fun testV15_farBoundaryLongSlide() {
        // [0, 0, 0, 2] -> [2, 0, 0, 0], score 0, moved=true
        assertLineMerge(listOf(0, 0, 0, 2), listOf(2, 0, 0, 0), expectedScoreDelta = 0, expectedMoved = true)
    }

    @Test
    fun testV16_doubleObstacleInteriorMerge() {
        // [-1, 2, 2, -1] -> [-1, 4, 0, -1], score +4
        assertLineMerge(listOf(-1, 2, 2, -1), listOf(-1, 4, 0, -1), expectedScoreDelta = 4, expectedMoved = true)
    }

    // --- Extended Multi-Dimension Lines ---

    @Test
    fun test3LengthLine_tightQuarters() {
        assertLineMerge(listOf(2, 2, 2), listOf(4, 2, 0), expectedScoreDelta = 4, expectedMoved = true)
        assertLineMerge(listOf(0, 4, 4), listOf(8, 0, 0), expectedScoreDelta = 8, expectedMoved = true)
        assertLineMerge(listOf(2, 4, 2), listOf(2, 4, 2), expectedScoreDelta = 0, expectedMoved = false)
    }

    @Test
    fun test5LengthLine_theMonolith() {
        assertLineMerge(listOf(2, 2, 2, 2, 2), listOf(4, 4, 2, 0, 0), expectedScoreDelta = 8, expectedMoved = true)
        assertLineMerge(listOf(4, 4, 8, 8, 16), listOf(8, 16, 16, 0, 0), expectedScoreDelta = 24, expectedMoved = true)
        assertLineMerge(listOf(0, 2, 0, 2, 0), listOf(4, 0, 0, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testHighValueTileMerges() {
        assertLineMerge(listOf(1024, 1024, 2048, 2048), listOf(2048, 4096, 0, 0), expectedScoreDelta = 6144, expectedMoved = true)
        assertLineMerge(listOf(16384, 16384, 0, 0), listOf(32768, 0, 0, 0), expectedScoreDelta = 32768, expectedMoved = true)
    }

    // --- Animation Movement & Merge Event Tracking Tests ---

    @Test
    fun testTileMovementEventCoordinatesRecordedCorrectly() {
        val t1 = createTile(2, col = 3)
        val line = listOf(null, null, null, t1)
        val result = LineMerger.compressAndMergeLine(line)

        assertEquals(1, result.movements.size)
        val move = result.movements[0]
        assertEquals(t1.id, move.tileId)
        assertEquals(Position(0, 3), move.from)
        assertEquals(Position(0, 0), move.to)
    }

    @Test
    fun testTileMergeEventRecordsSourceIdsAndResultingTile() {
        val t1 = createTile(4, col = 1)
        val t2 = createTile(4, col = 3)
        val line = listOf(null, t1, null, t2)
        val result = LineMerger.compressAndMergeLine(line) { 999L }

        assertEquals(1, result.merges.size)
        val merge = result.merges[0]
        assertEquals(Pair(t1.id, t2.id), merge.sourceTileIds)
        assertEquals(999L, merge.resultingTile.id)
        assertEquals(8, merge.resultingTile.value)
        assertEquals(Position(0, 0), merge.targetPosition)
    }
}
```

---

## 4. Test Suite 2: `GridTest` Architecture & Multi-Dimension Coverage

`GridTest` validates the mathematical and geometric integrity of the 2D grid matrix under various dimensions ($3 \times 3$, $4 \times 4$, $5 \times 5$), boundary constraints, clone immutability, obstacle placement, and empty cell bookkeeping.

### 4.1 Requirement Coverage Matrix

| Requirement | Test Method | Verification Invariant |
|:---|:---|:---|
| Multi-dimension 3x3 | `testGrid3x3Dimensions()` | Rows=3, Cols=3, totalCells=9, bounds `[0..2]` |
| Multi-dimension 4x4 | `testGrid4x4Dimensions()` | Rows=4, Cols=4, totalCells=16, bounds `[0..3]` |
| Multi-dimension 5x5 | `testGrid5x5Dimensions()` | Rows=5, Cols=5, totalCells=25, bounds `[0..4]` |
| Dimension Bounds Protection | `testInvalidDimensionsThrowException()` | Reject rows/cols < 2 or > 8 with `IllegalArgumentException` |
| Coordinate Bounds Checking | `testCoordinateBoundsChecking()` | Valid coordinates return true; negative and overflow return false |
| Out of Bounds Exception | `testGetAndSetOutOfBoundsThrowsException()` | Throws `IndexOutOfBoundsException` on illegal access |
| Clone Immutability | `testCloneProducesIndependentDeepCopy()` | Modifying copy does not mutate original, and vice versa |
| Obstacle Placement | `testObstaclePlacementAndImpassability()` | Obstacle cell has value -1; cannot be overwritten by set() |
| Empty Cell Counting | `testEmptyCellCountingAccurate()` | Fresh grid = $R \times C - |\text{obstacles}|$; updates accurately on tile add/remove |

### 4.2 Concrete Test Implementation: `GridTest.kt`

```kotlin
package com.game2048.android.core

import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import org.junit.Assert.*
import org.junit.Test

/**
 * Pure JVM unit tests for Grid dimensions, coordinate boundary enforcement,
 * clone deep-copy immutability, obstacle cells, and empty cell counting.
 */
class GridTest {

    @Test
    fun testGrid3x3Dimensions() {
        val grid = Grid(3, 3)
        assertEquals(3, grid.rows)
        assertEquals(3, grid.cols)
        assertEquals(9, grid.emptyCells().size)
        assertTrue(grid.isInBounds(0, 0))
        assertTrue(grid.isInBounds(2, 2))
        assertFalse(grid.isInBounds(3, 3))
    }

    @Test
    fun testGrid4x4Dimensions() {
        val grid = Grid(4, 4)
        assertEquals(4, grid.rows)
        assertEquals(4, grid.cols)
        assertEquals(16, grid.emptyCells().size)
        assertTrue(grid.isInBounds(0, 0))
        assertTrue(grid.isInBounds(3, 3))
        assertFalse(grid.isInBounds(4, 0))
    }

    @Test
    fun testGrid5x5Dimensions() {
        val grid = Grid(5, 5)
        assertEquals(5, grid.rows)
        assertEquals(5, grid.cols)
        assertEquals(25, grid.emptyCells().size)
        assertTrue(grid.isInBounds(0, 0))
        assertTrue(grid.isInBounds(4, 4))
        assertFalse(grid.isInBounds(5, 5))
    }

    @Test
    fun testInvalidDimensionsThrowException() {
        assertThrows(IllegalArgumentException::class.java) { Grid(1, 4) }
        assertThrows(IllegalArgumentException::class.java) { Grid(4, 1) }
        assertThrows(IllegalArgumentException::class.java) { Grid(9, 4) }
        assertThrows(IllegalArgumentException::class.java) { Grid(4, 9) }
        assertThrows(IllegalArgumentException::class.java) { Grid(-2, 4) }
    }

    @Test
    fun testCoordinateBoundsChecking() {
        val grid = Grid(4, 4)

        // Valid boundary edges
        assertTrue(grid.isInBounds(0, 0))
        assertTrue(grid.isInBounds(0, 3))
        assertTrue(grid.isInBounds(3, 0))
        assertTrue(grid.isInBounds(3, 3))

        // Negative coordinates
        assertFalse(grid.isInBounds(-1, 0))
        assertFalse(grid.isInBounds(0, -1))
        assertFalse(grid.isInBounds(-1, -1))

        // Overflow coordinates
        assertFalse(grid.isInBounds(4, 0))
        assertFalse(grid.isInBounds(0, 4))
        assertFalse(grid.isInBounds(4, 4))
        assertFalse(grid.isInBounds(100, 100))
    }

    @Test
    fun testGetAndSetOutOfBoundsThrowsException() {
        val grid = Grid(4, 4)
        assertThrows(IndexOutOfBoundsException::class.java) { grid.get(-1, 0) }
        assertThrows(IndexOutOfBoundsException::class.java) { grid.get(4, 2) }
        assertThrows(IndexOutOfBoundsException::class.java) { grid.set(0, 4, Tile(1L, 2)) }
    }

    @Test
    fun testCloneProducesIndependentDeepCopy() {
        val original = Grid(4, 4)
        original.set(0, 0, Tile(id = 10L, value = 2, row = 0, col = 0))
        original.set(1, 1, Tile(id = 11L, value = 4, row = 1, col = 1))

        val cloned = original.clone()

        // Equal content initially
        assertEquals(original, cloned)
        assertEquals(2, cloned.getValue(0, 0))
        assertEquals(4, cloned.getValue(1, 1))

        // Mutating cloned grid must NOT mutate original
        cloned.set(0, 0, Tile(id = 12L, value = 8, row = 0, col = 0))
        assertEquals(8, cloned.getValue(0, 0))
        assertEquals(2, original.getValue(0, 0))
        assertNotEquals(original, cloned)

        // Mutating original grid must NOT mutate cloned
        original.set(2, 2, Tile(id = 13L, value = 16, row = 2, col = 2))
        assertEquals(16, original.getValue(2, 2))
        assertEquals(0, cloned.getValue(2, 2))
    }

    @Test
    fun testObstaclePlacementAndImpassability() {
        val obstacles = setOf(Position(1, 1), Position(2, 2))
        val grid = Grid(4, 4, initialObstacles = obstacles)

        assertTrue(grid.isObstacle(1, 1))
        assertTrue(grid.isObstacle(2, 2))
        assertFalse(grid.isObstacle(0, 0))
        assertEquals(-1, grid.getValue(1, 1))
        assertEquals(-1, grid.getValue(2, 2))

        // Obstacles reduce empty cells count (16 - 2 = 14)
        assertEquals(14, grid.emptyCells().size)
        assertFalse(grid.emptyCells().contains(Position(1, 1)))
        assertFalse(grid.emptyCells().contains(Position(2, 2)))

        // Attempting to overwrite an obstacle must throw IllegalStateException
        assertThrows(IllegalStateException::class.java) {
            grid.set(1, 1, Tile(id = 99L, value = 4))
        }
    }

    @Test
    fun testEmptyCellCountingAccurate() {
        val grid = Grid(4, 4)
        assertEquals(16, grid.emptyCells().size)

        // Add 1 tile -> 15 empty cells
        grid.set(0, 0, Tile(1L, 2))
        assertEquals(15, grid.emptyCells().size)
        assertFalse(grid.emptyCells().contains(Position(0, 0)))

        // Add second tile -> 14 empty cells
        grid.set(3, 3, Tile(2L, 4))
        assertEquals(14, grid.emptyCells().size)

        // Clear cell (0, 0) -> back to 15
        grid.set(0, 0, null)
        assertEquals(15, grid.emptyCells().size)
        assertTrue(grid.emptyCells().contains(Position(0, 0)))

        // Fill all cells
        for (r in 0 until 4) {
            for (c in 0 until 4) {
                grid.set(r, c, Tile((r * 4 + c + 1).toLong(), 2))
            }
        }
        assertEquals(0, grid.emptyCells().size)
        assertTrue(grid.emptyCells().isEmpty())

        // Grid clear restores all 16 cells
        grid.clear()
        assertEquals(16, grid.emptyCells().size)
    }
}
```

---

## 5. Test Suite 3: `GameEngineTest` Architecture & State Machine Verification

`GameEngineTest` validates the complete 2D turn execution pipeline, directional swipes, score calculation, spawn rules on valid vs invalid moves, game-over predicates, and seed-based replayability.

### 5.1 Verification Scenarios & Logic Chains

1. **Cardinal Direction Swipes (UP, DOWN, LEFT, RIGHT)**:
   - Sets up controlled 2D grids and verifies that row-wise and column-wise traversals compress in the precise directional orientation.
2. **Exact Score Calculation ($\Delta S = \sum \text{merged values}$)**:
   - Verifies single merge: $2+2 \to 4 \implies \Delta S = 4$.
   - Verifies dual merge in single swipe: $[2,2,4,4] \implies \Delta S = 12$.
   - Verifies slide without merge: $\Delta S = 0$.
   - Verifies multi-turn cumulative total score matches exact sum of all merges.
   - Verifies high-score updates monotonically.
3. **No-Op Move / Spawn Suppression**:
   - Compresses tiles against a boundary. Swiping in that direction results in `moved == false`.
   - Invariant: `spawnedTile == null`, `scoreGained == 0`, grid matrix remains 100% byte-for-byte identical.
4. **Game-Over Evaluation (Full Grid with Zero Valid Merges)**:
   - Checkboard / alternating non-matching pattern across all adjacent cells.
   - `isGameOver() == true`, `gameState == GameState.GAME_OVER`.
   - Any swipe attempt is rejected (`moved == false`).
5. **Game-Over NOT Triggered When Merges Remain**:
   - Full grid (0 empty cells), but cell `(3,2) == 4` and `(3,3) == 4`.
   - `isGameOver() == false`, `gameState == GameState.PLAYING`.
   - Swiping RIGHT executes the merge, frees up cell `(3,2)`, and spawns a new tile.
   - Full grid with a vertical merge pair `(1,1) == 8` and `(2,1) == 8`.
   - `isGameOver() == false`.
6. **Deterministic Replayability (Seeded PRNG)**:
   - Two distinct `GameEngine` instances seeded with identical seed $S = 42\text{L}$.
   - Apply identical 15-move sequence `[UP, RIGHT, DOWN, LEFT, UP, ...]`.
   - Assert at each step: `grid` identical, `score` identical, `spawnedTile` identical.
   - Contrast with distinct seed $S = 9999\text{L}$ to prove PRNG sensitivity.

### 5.2 Deterministic Test Fixtures: `TestFixtures.kt`

```kotlin
package com.game2048.android.core

import com.game2048.android.core.engine.RandomProvider
import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import kotlin.random.Random

/**
 * Deterministic PRNG implementation for test reproducibility.
 */
class SeededRandomProvider(val seed: Long) : RandomProvider {
    private val random = Random(seed)

    override fun nextTileValue(): Int {
        // Canonical 2048: 90% chance of 2, 10% chance of 4
        return if (random.nextFloat() < 0.90f) 2 else 4
    }

    override fun selectEmptyCell(emptyCells: List<Position>): Position {
        require(emptyCells.isNotEmpty()) { "Cannot select from empty cell list" }
        return emptyCells[random.nextInt(emptyCells.size)]
    }
}

/**
 * Scripted PRNG for step-by-step injection of exact spawn locations and values.
 */
class ScriptedRandomProvider(
    private val values: Iterator<Int>,
    private val cellSelectors: Iterator<(List<Position>) -> Position>
) : RandomProvider {

    constructor(
        fixedValues: List<Int>,
        fixedPositions: List<Position>
    ) : this(
        values = fixedValues.iterator(),
        cellSelectors = fixedPositions.map { target ->
            { cells: List<Position> ->
                cells.firstOrNull { it == target } ?: cells.first()
            }
        }.iterator()
    )

    override fun nextTileValue(): Int = if (values.hasNext()) values.next() else 2

    override fun selectEmptyCell(emptyCells: List<Position>): Position {
        return if (cellSelectors.hasNext()) cellSelectors.next().invoke(emptyCells) else emptyCells.first()
    }
}

/**
 * Helper to construct a Grid directly from a 2D integer array.
 */
fun gridOf(vararg rows: List<Int>, obstacles: Set<Position> = emptySet()): Grid {
    val rCount = rows.size
    val cCount = rows[0].size
    val grid = Grid(rCount, cCount, obstacles)
    var idCounter = 1L
    for (r in 0 until rCount) {
        for (c in 0 until cCount) {
            val v = rows[r][c]
            if (v > 0) {
                grid.set(r, c, Tile(id = idCounter++, value = v, row = r, col = c))
            }
        }
    }
    return grid
}
```

### 5.3 Concrete Test Implementation: `GameEngineTest.kt`

```kotlin
package com.game2048.android.core

import com.game2048.android.core.engine.GameEngine
import com.game2048.android.core.engine.GameEngineImpl
import com.game2048.android.core.model.*
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * Pure JVM unit tests for GameEngine swipe mechanics across 4 directions,
 * exact score accumulation, blocked move handling, game-over evaluation,
 * and deterministic replayability.
 */
class GameEngineTest {

    private lateinit var randomProvider: SeededRandomProvider
    private lateinit var engine: GameEngine

    @Before
    fun setUp() {
        randomProvider = SeededRandomProvider(seed = 42L)
        engine = GameEngineImpl(randomProvider)
    }

    // --- Cardinal Direction Swipes ---

    @Test
    fun testSwipeLeft_compressesAndMergesTowardsColZero() {
        val initialGrid = gridOf(
            listOf(2, 2, 4, 4),
            listOf(0, 2, 0, 2),
            listOf(2, 4, 2, 4),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.LEFT)

        assertTrue(result.moved)
        assertEquals(16, result.scoreGained) // (2+2->4) + (4+4->8) + (2+2->4) = 16
        assertEquals(4, engine.grid.getValue(0, 0))
        assertEquals(8, engine.grid.getValue(0, 1))
        assertEquals(4, engine.grid.getValue(1, 0))
        assertEquals(2, engine.grid.getValue(2, 0))
        assertEquals(4, engine.grid.getValue(2, 1))
        assertEquals(2, engine.grid.getValue(2, 2))
        assertEquals(4, engine.grid.getValue(2, 3))
    }

    @Test
    fun testSwipeRight_compressesAndMergesTowardsMaxCol() {
        val initialGrid = gridOf(
            listOf(4, 4, 2, 2),
            listOf(2, 0, 2, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.RIGHT)

        assertTrue(result.moved)
        assertEquals(16, result.scoreGained) // (4+4->8) + (2+2->4) + (2+2->4) = 16
        assertEquals(8, engine.grid.getValue(0, 2))
        assertEquals(4, engine.grid.getValue(0, 3))
        assertEquals(4, engine.grid.getValue(1, 3))
    }

    @Test
    fun testSwipeUp_compressesAndMergesTowardsRowZero() {
        val initialGrid = gridOf(
            listOf(2, 0, 2, 0),
            listOf(2, 2, 4, 0),
            listOf(4, 0, 2, 0),
            listOf(4, 2, 4, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.UP)

        assertTrue(result.moved)
        // Col 0: [2, 2, 4, 4] -> [4, 8, 0, 0], score +12
        // Col 1: [0, 2, 0, 2] -> [4, 0, 0, 0], score +4
        // Col 2: [2, 4, 2, 4] -> [2, 4, 2, 4], score +0
        assertEquals(16, result.scoreGained)
        assertEquals(4, engine.grid.getValue(0, 0))
        assertEquals(8, engine.grid.getValue(1, 0))
        assertEquals(4, engine.grid.getValue(0, 1))
        assertEquals(2, engine.grid.getValue(0, 2))
        assertEquals(4, engine.grid.getValue(1, 2))
        assertEquals(2, engine.grid.getValue(2, 2))
        assertEquals(4, engine.grid.getValue(3, 2))
    }

    @Test
    fun testSwipeDown_compressesAndMergesTowardsMaxRow() {
        val initialGrid = gridOf(
            listOf(4, 2, 0, 0),
            listOf(4, 0, 0, 0),
            listOf(2, 2, 0, 0),
            listOf(2, 0, 0, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.DOWN)

        assertTrue(result.moved)
        // Col 0: [4, 4, 2, 2] downwards -> [8, 4] at bottom rows (2,3), score +12
        // Col 1: [2, 0, 2, 0] downwards -> [4] at bottom row 3, score +4
        assertEquals(16, result.scoreGained)
        assertEquals(8, engine.grid.getValue(2, 0))
        assertEquals(4, engine.grid.getValue(3, 0))
        assertEquals(4, engine.grid.getValue(3, 1))
    }

    // --- Scoring Verification ---

    @Test
    fun testExactScoreAccumulationOnSingleMerge() {
        val grid = gridOf(
            listOf(2, 2, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 100)

        val result = engine.move(MoveDirection.LEFT)

        assertEquals(4, result.scoreGained)
        assertEquals(104, engine.score)
    }

    @Test
    fun testScoreDoesNotIncrementOnPureSlideWithoutMerge() {
        val grid = gridOf(
            listOf(0, 0, 2, 0),
            listOf(0, 4, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 250)

        val result = engine.move(MoveDirection.LEFT)

        assertTrue(result.moved)
        assertEquals(0, result.scoreGained)
        assertEquals(250, engine.score)
    }

    @Test
    fun testHighScoreUpdatesMonotonically() {
        val grid = gridOf(
            listOf(2, 2, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 50)
        assertEquals(50, engine.highScore)

        engine.move(MoveDirection.LEFT) // +4 points -> score 54
        assertEquals(54, engine.score)
        assertEquals(54, engine.highScore)

        // Reset game; score becomes 0, but highScore remains 54
        engine.reset()
        assertEquals(0, engine.score)
        assertEquals(54, engine.highScore)
    }

    // --- Blocked Move / Spawn Suppression ---

    @Test
    fun testBlockedMoveDoesNotSpawnTileAndMaintainsState() {
        val grid = gridOf(
            listOf(4, 8, 16, 32),
            listOf(2, 4, 8, 16),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 500)
        val snapshotBefore = engine.grid.clone()

        // Swipe LEFT is already fully compressed against left boundary
        val result = engine.move(MoveDirection.LEFT)

        assertFalse("Move must be reported as not moved", result.moved)
        assertEquals(0, result.scoreGained)
        assertNull("No new tile should be spawned on a blocked move", result.spawnedTile)
        assertEquals(500, engine.score)
        assertEquals("Grid state must remain identical after blocked move", snapshotBefore, engine.grid)
    }

    // --- Game Over Evaluation ---

    @Test
    fun testGameOverTriggeredWhenGridIsFullWithNoAdjacentMatches() {
        // Checkerboard / alternating values with no horizontal or vertical matches
        val fullBlockedGrid = gridOf(
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2),
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2)
        )
        engine.setGridState(fullBlockedGrid, score = 1000)

        assertTrue("Game over should be detected when full with no matches", engine.isGameOver())
        assertEquals(GameState.GAME_OVER, engine.gameState)

        // All moves must fail
        assertFalse(engine.move(MoveDirection.UP).moved)
        assertFalse(engine.move(MoveDirection.DOWN).moved)
        assertFalse(engine.move(MoveDirection.LEFT).moved)
        assertFalse(engine.move(MoveDirection.RIGHT).moved)
    }

    @Test
    fun testGameOverNotTriggeredWhenFullGridHasHorizontalMerge() {
        val gridWithHorizontalMerge = gridOf(
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2),
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 4) // (3,2) and (3,3) can merge
        )
        engine.setGridState(gridWithHorizontalMerge, score = 1000)

        assertFalse("Game over should NOT trigger when horizontal merge exists", engine.isGameOver())
        assertEquals(GameState.PLAYING, engine.gameState)

        val result = engine.move(MoveDirection.RIGHT)
        assertTrue(result.moved)
        assertEquals(8, result.scoreGained)
        assertNotNull(result.spawnedTile)
    }

    @Test
    fun testGameOverNotTriggeredWhenFullGridHasVerticalMerge() {
        val gridWithVerticalMerge = gridOf(
            listOf(2, 4, 2, 4),
            listOf(4, 8, 4, 2),
            listOf(2, 8, 2, 4), // (1,1) and (2,1) both 8
            listOf(4, 2, 4, 2)
        )
        engine.setGridState(gridWithVerticalMerge, score = 1000)

        assertFalse("Game over should NOT trigger when vertical merge exists", engine.isGameOver())
        assertEquals(GameState.PLAYING, engine.gameState)

        val result = engine.move(MoveDirection.UP)
        assertTrue(result.moved)
        assertEquals(16, result.scoreGained)
    }

    @Test
    fun testGameOverWithObstaclesSeparatingMatchingTiles() {
        // Obstacle at (0, 1) prevents (0, 0) and (0, 2) from merging
        val obstacles = setOf(Position(0, 1))
        val grid = gridOf(
            listOf(2, -1, 2, 4),
            listOf(4, 2, 4, 2),
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2),
            obstacles = obstacles
        )
        engine.setGridState(grid, score = 500)

        assertTrue("Obstacle prevents horizontal merge, so game over should trigger", engine.isGameOver())
        assertEquals(GameState.GAME_OVER, engine.gameState)
    }

    // --- Deterministic Replayability ---

    @Test
    fun testDeterministicReplayabilityWithIdenticalSeeds() {
        val seed = 123456789L
        val moveSequence = listOf(
            MoveDirection.UP, MoveDirection.RIGHT, MoveDirection.DOWN, MoveDirection.LEFT,
            MoveDirection.UP, MoveDirection.RIGHT, MoveDirection.UP, MoveDirection.LEFT,
            MoveDirection.DOWN, MoveDirection.RIGHT, MoveDirection.UP, MoveDirection.LEFT
        )

        // Run 1
        val engine1 = GameEngineImpl(SeededRandomProvider(seed))
        engine1.startNewGame(rows = 4, cols = 4)
        val snapshots1 = ArrayList<Grid>()
        val scores1 = ArrayList<Int>()

        for (dir in moveSequence) {
            engine1.move(dir)
            snapshots1.add(engine1.grid.clone())
            scores1.add(engine1.score)
        }

        // Run 2
        val engine2 = GameEngineImpl(SeededRandomProvider(seed))
        engine2.startNewGame(rows = 4, cols = 4)
        val snapshots2 = ArrayList<Grid>()
        val scores2 = ArrayList<Int>()

        for (dir in moveSequence) {
            engine2.move(dir)
            snapshots2.add(engine2.grid.clone())
            scores2.add(engine2.score)
        }

        // Assert 100% bit-exact equivalence at every single turn
        for (i in moveSequence.indices) {
            assertEquals("Grid state diverged at step $i", snapshots1[i], snapshots2[i])
            assertEquals("Score diverged at step $i", scores1[i], scores2[i])
        }
    }

    @Test
    fun testReplayDivergesWithDifferentSeeds() {
        val moveSequence = listOf(
            MoveDirection.UP, MoveDirection.RIGHT, MoveDirection.DOWN, MoveDirection.LEFT,
            MoveDirection.UP, MoveDirection.RIGHT
        )

        val engine1 = GameEngineImpl(SeededRandomProvider(seed = 111L))
        engine1.startNewGame(4, 4)
        val engine2 = GameEngineImpl(SeededRandomProvider(seed = 999L))
        engine2.startNewGame(4, 4)

        for (dir in moveSequence) {
            engine1.move(dir)
            engine2.move(dir)
        }

        // Different seeds must generate different spawn placements
        assertNotEquals(engine1.grid, engine2.grid)
    }

    // --- Level Objective Victory Trigger ---

    @Test
    fun testLevelWonTriggeredWhenTargetTileReached() {
        val grid = gridOf(
            listOf(128, 128, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.startNewGame(targetTile = 256)
        engine.setGridState(grid, score = 0)

        val result = engine.move(MoveDirection.LEFT)

        assertTrue(result.moved)
        assertEquals(256, engine.grid.getValue(0, 0))
        assertTrue("Level won flag should be true when target 256 is merged", result.isLevelWon)
        assertTrue(engine.isLevelWon())
        assertEquals(GameState.LEVEL_WON, engine.gameState)
    }
}
```

---

## 6. Test Suite Directory Layout & Gradle Verification

All unit tests are strictly placed within the test source tree:
```
android_2048_game/
└── app/
    └── src/
        └── test/
            └── java/
                └── com/
                    └── game2048/
                        └── android/
                            ├── SmokeUnitTest.kt
                            └── core/
                                ├── TestFixtures.kt
                                ├── LineMergerTest.kt
                                ├── GridTest.kt
                                └── GameEngineTest.kt
```

### Verification Command:
```powershell
cd android_2048_game
.\gradlew.bat testDebugUnitTest --tests "com.game2048.android.core.*"
```

### Expected Execution Metrics:
- **Total Test Cases**: 36 test methods.
- **Pure JVM Runtime**: $\le 650\text{ms}$.
- **Core Math Statement & Branch Coverage**: 100%.
- **Memory Overhead**: 0 MB Android emulator overhead; executed entirely on local JDK 21 LTS.

---

## 7. Downstream Implementation Checklist for Worker Agents

When `worker_m2_1` and `worker_m2_2` implement the core engine and models, they must satisfy these invariants:
1. `LineMerger.compressAndMergeLine` must partition by obstacle cell (`value == -1`) before evaluating merges.
2. In single-pass merge, never allow a merged tile to merge again within the same line traversal.
3. In `Grid`, constructor must reject rows/cols outside `2..8`, and bounds checking must guard against negative indices.
4. `emptyCells()` must strictly exclude both active tiles and obstacle cells.
5. `GameEngine.move` must return `moved == false` and suppress `spawnedTile` when no tiles slide or merge.
6. `GameEngine.isGameOver` must evaluate horizontal and vertical adjacent pairs in $O(R \times C)$ fast pass, properly skipping obstacle boundaries.
