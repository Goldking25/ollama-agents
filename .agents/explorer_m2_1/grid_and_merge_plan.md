# Milestone 2 Technical Specification: Grid Representation & 1D/2D Slide-and-Merge Engine

**Document:** `grid_and_merge_plan.md`  
**Author:** explorer_m2_1 (Grid Representation & 1D/2D Slide-and-Merge Algorithm Explorer)  
**Target Milestone:** Milestone 2 (Core 2048 Engine & Math Domain)  
**Status:** Approved Specification & Implementation Blueprint  
**Target Directory:** `e:\Learning\Python\agent_test\android_2048_game`  

---

## 1. Executive Summary & Design Principles

This specification delivers the exact, production-ready blueprint for the core 2048 game engine and domain data models for Milestone 2.

### Core Architectural Principles:
1. **Pure Kotlin Domain Model (Zero Android Framework Coupling)**:
   All models and engines in `com.game2048.android.core.model` and `com.game2048.android.core.engine` are implemented in pure Kotlin standard library (`kotlin.*`, `java.util.concurrent.atomic.AtomicLong`). They have zero references to `android.*` packages, ensuring:
   - Ultra-fast headless JVM unit test execution (< 500 ms for the entire suite).
   - Absolute determinism across platforms and environments.
   - Zero UI/view allocation during game logic evaluation.
2. **Deterministic Single-Pass Non-Double-Merge Invariant**:
   Enforces the canonical 2048 merge rules (`[2,2,4,4]->[4,8,0,0]`, `[2,2,2,0]->[4,2,0,0]`, `[4,2,2,0]->[4,4,0,0]`, `[2,0,2,4]->[4,4,0,0]`) via a single-pass pointer algorithm. Newly formed merged tiles cannot merge again in the same turn.
3. **Partitioned Obstacle Boundaries**:
   Impassable cells (`value = -1`) act as immovable walls, partitioning rows and columns into isolated sliding lanes. Tiles slide up to obstacles without crossing or merging into them.
4. **Comprehensive Animation Event Tracking**:
   The engine emits detailed, immutable records of all tile translations (`TileMovement`) and collisions (`TileMerge`), providing the exact inputs required by the two-phase `ValueAnimator` render pipeline in Milestone 4.
5. **Deterministic Randomness & Replayability**:
   Tile spawning relies on an injectable `RandomProvider` interface, allowing 100% reproducible test scenarios, anti-cheat validation, and replay logging.

---

## 2. Mathematical Formalization & Invariants

### 2.1 Coordinate System & State Space
- The grid is an $R \times C$ matrix $\mathcal{G} \in \mathbb{Z}^{R \times C}$ where $R, C \in [2, 8]$.
- Cell coordinates: $\text{Position}(r, c)$ where $r \in [0, R-1]$ (row, top-to-bottom) and $c \in [0, C-1]$ (column, left-to-right).
- State values for cell $(r, c)$:
  $$\mathcal{G}(r, c) = \begin{cases}
  0 & \text{Empty cell} \\
  2^k, \ k \in \{1, 2, \dots, 16\} & \text{Active playable tile } (2, 4, 8, \dots, 65536) \\
  -1 & \text{Impassable obstacle cell (fixed)}
  \end{cases}$$

### 2.2 Cardinal Direction Vectors
The 4 swipe directions $\mathcal{D} = \{\text{UP}, \text{DOWN}, \text{LEFT}, \text{RIGHT}\}$ are defined by displacement vectors:
$$\vec{d}_{\text{UP}} = (-1, 0), \quad \vec{d}_{\text{DOWN}} = (+1, 0), \quad \vec{d}_{\text{LEFT}} = (0, -1), \quad \vec{d}_{\text{RIGHT}} = (0, +1)$$

### 2.3 2D-to-1D Line Projection Mapping
To eliminate duplicate merge logic and directional branching, every 2D grid move is normalized to 1D lines that compress towards index 0:

| Direction | Outer Loop (Lines) | Line Length | Index $i \in [0, L-1]$ maps to $(r, c)$ | Traversal Intent |
|:---|:---|:---:|:---|:---|
| **LEFT** | Row $r \in [0, R-1]$ | $C$ | $\text{Position}(r, i)$ | Leftmost column is index 0 |
| **RIGHT** | Row $r \in [0, R-1]$ | $C$ | $\text{Position}(r, C - 1 - i)$ | Rightmost column is index 0 |
| **UP** | Col $c \in [0, C-1]$ | $R$ | $\text{Position}(i, c)$ | Topmost row is index 0 |
| **DOWN** | Col $c \in [0, C-1]$ | $R$ | $\text{Position}(R - 1 - i, c)$ | Bottommost row is index 0 |

### 2.4 Mutation Invariant & Spawning Trigger
Let $\mathcal{G}_t$ be the grid before the swipe, and $\mathcal{G}'_{t+1}$ be the grid after sliding and merging:
$$\text{HasChanged} \iff \text{tileMovements.isNotEmpty()} \lor \text{tileMerges.isNotEmpty()}$$
- If $\text{HasChanged} == \text{false}$: Swipe is a no-op. Score gained is 0, no tile spawns, game state does not advance.
- If $\text{HasChanged} == \text{true}$: Score updates by $\Delta S = \sum \text{merged values}$, and exactly 1 new tile spawns in a randomly selected empty cell (excluding obstacles).

---

## 3. Package Architecture & Class Diagram

The core module is organized into two pure Kotlin packages under `app/src/main/java`:

```
com.game2048.android.core
├── model/
│   ├── Position.kt              // Immutable 2D grid coordinate (row, col)
│   ├── MoveDirection.kt         // Cardinal directions: UP, DOWN, LEFT, RIGHT
│   ├── Tile.kt                  // Immutable tile identity (id, value, position)
│   ├── Grid.kt                  // Arbitrary R x C matrix with obstacle mask & deep copy
│   ├── TileMovement.kt          // Translation record (from, to, tileId, value)
│   ├── TileMerge.kt             // Collision record (sourcePair, resultingTile, targetPos)
│   └── MoveResult.kt            // Comprehensive turn summary and game flags
└── engine/
    ├── LineMerger.kt            // Pure 1D single-pass merge algorithm with obstacle partitioning
    ├── GridEngine.kt            // 2D grid orchestrator (swipe execution, spawn, scoring, game-over)
    ├── RandomProvider.kt        // Interface + Default / Seeded / Deterministic PRNG
    └── TileIdGenerator.kt       // Interface + AtomicLong sequential ID generator
```

---

## 4. Complete Pure Kotlin Data Models (`core.model`)

### 4.1 `Position.kt`
```kotlin
package com.game2048.android.core.model

/**
 * Immutable 2D grid coordinate.
 *
 * @property row 0-indexed row (0 is top, rows - 1 is bottom)
 * @property col 0-indexed column (0 is left, cols - 1 is right)
 */
data class Position(val row: Int, val col: Int) {

    /**
     * Returns an adjacent position displaced by the specified direction.
     */
    operator fun plus(direction: MoveDirection): Position =
        Position(row + direction.deltaRow, col + direction.deltaCol)

    /**
     * Returns an offset position.
     */
    fun offset(deltaRow: Int, deltaCol: Int): Position =
        Position(row + deltaRow, col + deltaCol)

    override fun toString(): String = "($row, $col)"
}
```

### 4.2 `MoveDirection.kt`
```kotlin
package com.game2048.android.core.model

/**
 * The four cardinal swipe directions supported by the game engine.
 *
 * @property deltaRow Vertical displacement vector (-1 for UP, +1 for DOWN, 0 otherwise)
 * @property deltaCol Horizontal displacement vector (-1 for LEFT, +1 for RIGHT, 0 otherwise)
 */
enum class MoveDirection(val deltaRow: Int, val deltaCol: Int) {
    UP(-1, 0),
    DOWN(1, 0),
    LEFT(0, -1),
    RIGHT(0, 1);

    val isVertical: Boolean get() = this == UP || this == DOWN
    val isHorizontal: Boolean get() = this == LEFT || this == RIGHT

    /**
     * Returns the opposite direction.
     */
    fun opposite(): MoveDirection = when (this) {
        UP -> DOWN
        DOWN -> UP
        LEFT -> RIGHT
        RIGHT -> LEFT
    }
}
```

### 4.3 `Tile.kt`
```kotlin
package com.game2048.android.core.model

/**
 * Immutable representation of a tile on the game board.
 * Maintains persistent identity ([id]) across turns to enable smooth UI animation interpolation.
 *
 * @property id Globally unique persistent identifier (> 0 for active tiles, -1 for obstacles)
 * @property value Tile value (power of 2: 2, 4, 8, ..., 65536; or [OBSTACLE_VALUE] = -1)
 * @property position Current 2D grid position of the tile
 */
data class Tile(
    val id: Long,
    val value: Int,
    val position: Position
) {
    /**
     * Secondary convenience constructor taking explicit row and col integers.
     */
    constructor(id: Long, value: Int, row: Int, col: Int) : this(id, value, Position(row, col))

    val row: Int get() = position.row
    val col: Int get() = position.col

    val isObstacle: Boolean get() = value == OBSTACLE_VALUE

    companion object {
        const val OBSTACLE_VALUE: Int = -1
        const val OBSTACLE_ID: Long = -1L

        /**
         * Creates an impassable obstacle tile at the given coordinate.
         */
        fun createObstacle(position: Position): Tile =
            Tile(id = OBSTACLE_ID, value = OBSTACLE_VALUE, position = position)

        fun createObstacle(row: Int, col: Int): Tile =
            createObstacle(Position(row, col))
    }
}
```

### 4.4 `Grid.kt`
```kotlin
package com.game2048.android.core.model

/**
 * Arbitrary-dimension 2D grid supporting standard sizes (3x3, 4x4, 5x5) and impassable obstacle cells.
 *
 * @property rows Number of rows (must be between 2 and 8 inclusive)
 * @property cols Number of columns (must be between 2 and 8 inclusive)
 * @property initialObstacles Optional set of coordinates configured as fixed obstacle cells (-1)
 */
class Grid(
    val rows: Int,
    val cols: Int,
    initialObstacles: Set<Position> = emptySet()
) {
    init {
        require(rows in MIN_DIMENSION..MAX_DIMENSION) {
            "Grid rows must be between $MIN_DIMENSION and $MAX_DIMENSION, got: $rows"
        }
        require(cols in MIN_DIMENSION..MAX_DIMENSION) {
            "Grid cols must be between $MIN_DIMENSION and $MAX_DIMENSION, got: $cols"
        }
        initialObstacles.forEach { pos ->
            require(isWithinBounds(pos)) {
                "Obstacle coordinate $pos is outside grid dimensions ($rows x $cols)"
            }
        }
    }

    private val cells: Array<Array<Tile?>> = Array(rows) { r ->
        Array(cols) { c ->
            val pos = Position(r, c)
            if (pos in initialObstacles) Tile.createObstacle(pos) else null
        }
    }

    val obstacles: Set<Position> = initialObstacles.toSet()

    operator fun get(row: Int, col: Int): Tile? {
        checkBounds(row, col)
        return cells[row][col]
    }

    operator fun get(position: Position): Tile? = get(position.row, position.col)

    /**
     * Returns the integer value at (row, col):
     * - 0 for empty cell
     * - -1 for obstacle
     * - value > 0 for active tile
     */
    fun getValue(row: Int, col: Int): Int = get(row, col)?.value ?: 0

    fun getValue(position: Position): Int = getValue(position.row, position.col)

    fun setTile(tile: Tile?) {
        if (tile != null) {
            checkBounds(tile.row, tile.col)
            require(!isObstacle(tile.row, tile.col) || tile.isObstacle) {
                "Cannot place active tile on obstacle cell at (${tile.row}, ${tile.col})"
            }
            cells[tile.row][tile.col] = tile
        }
    }

    fun setTile(row: Int, col: Int, tile: Tile?) {
        checkBounds(row, col)
        if (tile != null) {
            require(!isObstacle(row, col) || tile.isObstacle) {
                "Cannot place active tile on obstacle cell at ($row, $col)"
            }
            cells[row][col] = if (tile.position.row == row && tile.position.col == col) {
                tile
            } else {
                tile.copy(position = Position(row, col))
            }
        } else {
            require(!isObstacle(row, col)) {
                "Cannot clear fixed obstacle cell at ($row, $col)"
            }
            cells[row][col] = null
        }
    }

    fun clearCell(row: Int, col: Int) {
        setTile(row, col, null)
    }

    fun clearCell(position: Position) {
        clearCell(position.row, position.col)
    }

    fun isWithinBounds(row: Int, col: Int): Boolean =
        row in 0 until rows && col in 0 until cols

    fun isWithinBounds(position: Position): Boolean =
        isWithinBounds(position.row, position.col)

    fun isEmpty(row: Int, col: Int): Boolean = getValue(row, col) == 0

    fun isEmpty(position: Position): Boolean = isEmpty(position.row, position.col)

    fun isObstacle(row: Int, col: Int): Boolean = getValue(row, col) == Tile.OBSTACLE_VALUE

    fun isObstacle(position: Position): Boolean = isObstacle(position.row, position.col)

    fun isOccupied(row: Int, col: Int): Boolean = getValue(row, col) > 0

    fun isOccupied(position: Position): Boolean = isOccupied(position.row, position.col)

    /**
     * Returns all coordinates that are empty (value == 0), strictly excluding obstacles.
     */
    fun getEmptyPositions(): List<Position> {
        val emptyList = mutableListOf<Position>()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                if (isEmpty(r, c)) {
                    emptyList.add(Position(r, c))
                }
            }
        }
        return emptyList
    }

    /**
     * Returns all active playable tiles (value > 0), strictly excluding obstacles.
     */
    fun getAllTiles(): List<Tile> {
        val tiles = mutableListOf<Tile>()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val t = cells[r][c]
                if (t != null && !t.isObstacle) {
                    tiles.add(t)
                }
            }
        }
        return tiles
    }

    /**
     * Creates an independent deep copy of this grid.
     */
    fun copy(): Grid {
        val newGrid = Grid(rows, cols, obstacles)
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val t = cells[r][c]
                if (t != null && !t.isObstacle) {
                    newGrid.cells[r][c] = t.copy()
                }
            }
        }
        return newGrid
    }

    private fun checkBounds(row: Int, col: Int) {
        require(isWithinBounds(row, col)) {
            "Cell coordinate ($row, $col) is outside grid bounds ($rows x $cols)"
        }
    }

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is Grid) return false
        if (rows != other.rows || cols != other.cols) return false
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
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                result = 31 * result + getValue(r, c).hashCode()
            }
        }
        return result
    }

    override fun toString(): String = buildString {
        append("Grid(${rows}x${cols}):\n")
        for (r in 0 until rows) {
            append("[")
            for (c in 0 until cols) {
                val v = getValue(r, c)
                val s = when (v) {
                    0 -> "."
                    Tile.OBSTACLE_VALUE -> "X"
                    else -> v.toString()
                }
                append(s.padStart(5))
                if (c < cols - 1) append(", ")
            }
            append("]\n")
        }
    }

    companion object {
        const val MIN_DIMENSION = 2
        const val MAX_DIMENSION = 8

        /**
         * Factory helper to construct a grid with a predefined matrix of integer values.
         * Useful for concise unit tests.
         */
        fun fromValues(values: Array<IntArray>, obstacles: Set<Position> = emptySet()): Grid {
            val rCount = values.size
            val cCount = values[0].size
            val grid = Grid(rCount, cCount, obstacles)
            var idCounter = 1L
            for (r in 0 until rCount) {
                for (c in 0 until cCount) {
                    val v = values[r][c]
                    if (v > 0) {
                        grid.setTile(Tile(idCounter++, v, r, c))
                    } else if (v == Tile.OBSTACLE_VALUE && !grid.isObstacle(r, c)) {
                        // Dynamically mark obstacle if provided in matrix
                        grid.cells[r][c] = Tile.createObstacle(r, c)
                    }
                }
            }
            return grid
        }
    }
}
```

### 4.5 `TileMovement.kt`
```kotlin
package com.game2048.android.core.model

/**
 * Represents the translation of a tile from an initial position to a target position.
 * Emitted during the slide phase to drive translation animations.
 *
 * @property from Origin coordinate of the tile before the swipe
 * @property to Destination coordinate of the tile after the swipe
 * @property tileId Unique identity of the moving tile
 * @property value Numerical face value of the moving tile
 */
data class TileMovement(
    val from: Position,
    val to: Position,
    val tileId: Long,
    val value: Int
) {
    init {
        require(from != to) {
            "TileMovement from and to positions must not be identical: $from"
        }
    }
}
```

### 4.6 `TileMerge.kt`
```kotlin
package com.game2048.android.core.model

/**
 * Represents the collision and fusion of two tiles into a new tile of double value.
 * Emitted to trigger the merge-pop overshoot animation in the UI layer.
 *
 * @property sourceTileIds Identifiers of the two source tiles that merged
 * @property resultingTile The newly generated tile instance with value = source1.value + source2.value
 * @property targetPosition The cell where the collision occurred (equals resultingTile.position)
 */
data class TileMerge(
    val sourceTileIds: Pair<Long, Long>,
    val resultingTile: Tile,
    val targetPosition: Position
) {
    val mergedValue: Int get() = resultingTile.value
}
```

### 4.7 `MoveResult.kt`
```kotlin
package com.game2048.android.core.model

/**
 * Immutable turn summary returned after evaluating a directional swipe.
 *
 * @property moved True if at least one tile translated or merged; false if the swipe was a no-op
 * @property scoreGained Points awarded from merges during this turn (0 if moved is false)
 * @property tileMovements List of all tile translations (for Phase 1 slide animations)
 * @property tileMerges List of all tile merges (for Phase 2 merge-pop animations)
 * @property spawnedTile Newly created tile, or null if no move occurred or grid is full
 * @property isGameOver True if no legal moves remain in any of the 4 directions
 * @property isLevelWon True if any tile on the board has reached or exceeded the target tile
 */
data class MoveResult(
    val moved: Boolean,
    val scoreGained: Int,
    val tileMovements: List<TileMovement>,
    val tileMerges: List<TileMerge>,
    val spawnedTile: Tile?,
    val isGameOver: Boolean,
    val isLevelWon: Boolean
) {
    companion object {
        fun noMove(isGameOver: Boolean = false, isLevelWon: Boolean = false): MoveResult =
            MoveResult(
                moved = false,
                scoreGained = 0,
                tileMovements = emptyList(),
                tileMerges = emptyList(),
                spawnedTile = null,
                isGameOver = isGameOver,
                isLevelWon = isLevelWon
            )
    }
}
```

---

## 5. Core Engine Algorithms (`core.engine`)

### 5.1 `LineMerger.kt`
The `LineMerger` is a pure functional component that compresses and merges a 1D array of cells towards index 0.

#### Algorithm Specification:
1. **Obstacle Detection & Domain Partitioning**:
   - The line is partitioned into independent sub-segments bounded by obstacle cells (`value = -1`).
   - If an obstacle exists at index $k$, subsegment $[0 .. k-1]$ is processed, obstacle remains fixed at index $k$, and subsegment $[k+1 .. L-1]$ is processed.
   - Tiles cannot slide across or merge into obstacle cells.
2. **Single-Pass Compress & Merge (per segment $[start .. end]$)**:
   - Collect all active tiles ($value > 0$) in order with their current indices: `nonEmpties`.
   - Initialize pointer `targetIdx = start`, `i = 0`.
   - While $i < |\text{nonEmpties}|$:
     - Let $T_1 = \text{nonEmpties}[i]$.
     - If $i + 1 < |\text{nonEmpties}|$ AND $T_1.\text{value} == \text{nonEmpties}[i+1].\text{value}$:
       - **Merge**:
         - Resulting value: $V_{\text{merged}} = T_1.\text{value} \times 2$.
         - Target position: $P_{\text{target}} = \text{positions}[targetIdx]$.
         - Emit `TileMerge(Pair(T1.id, T2.id), resultingTile, P_target)`.
         - If $T_1.\text{origIdx} \ne targetIdx$, emit `TileMovement` for $T_1$.
         - Emit `TileMovement` for $T_2$ (always moved).
         - Score delta: $+ V_{\text{merged}}$.
         - Advance: $targetIdx \leftarrow targetIdx + 1$, $i \leftarrow i + 2$ (strictly prevents re-merging).
     - Else:
       - **Slide**:
         - Target position: $P_{\text{target}} = \text{positions}[targetIdx]$.
         - If $T_1.\text{origIdx} \ne targetIdx$, emit `TileMovement` for $T_1$.
         - Advance: $targetIdx \leftarrow targetIdx + 1$, $i \leftarrow i + 1$.
   - Any remaining cells in $[targetIdx .. end]$ are populated with `null`.

#### Complete Implementation:
```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import com.game2048.android.core.model.TileMerge
import com.game2048.android.core.model.TileMovement

object LineMerger {

    data class LineResult(
        val newLine: List<Tile?>,
        val movements: List<TileMovement>,
        val merges: List<TileMerge>,
        val scoreGained: Int
    )

    /**
     * Compresses and merges a 1D line towards index 0.
     * Enforces the single-pass non-double-merge invariant and obstacle partitioning.
     *
     * @param line Tiles in the line (null for empty, value = -1 for obstacle)
     * @param positions 2D positions corresponding to each index in [line]
     * @param idGenerator Provider of globally unique IDs for newly created merged tiles
     */
    fun compressAndMergeLine(
        line: List<Tile?>,
        positions: List<Position> = line.indices.map { Position(0, it) },
        idGenerator: () -> Long
    ): LineResult {
        require(line.size == positions.size) {
            "Line size (${line.size}) must match positions size (${positions.size})"
        }

        val n = line.size
        val resultLine = arrayOfNulls<Tile>(n)
        val movements = mutableListOf<TileMovement>()
        val merges = mutableListOf<TileMerge>()
        var totalScore = 0

        var segStart = 0
        for (i in 0 until n) {
            val tile = line[i]
            if (tile != null && tile.isObstacle) {
                // Process playable segment before obstacle
                if (segStart < i) {
                    val segResult = processSegment(line, positions, segStart, i - 1, idGenerator)
                    for (k in segStart until i) {
                        resultLine[k] = segResult.newLine[k]
                    }
                    movements.addAll(segResult.movements)
                    merges.addAll(segResult.merges)
                    totalScore += segResult.scoreGained
                }
                // Fix obstacle at current index
                resultLine[i] = tile
                segStart = i + 1
            }
        }

        // Process final segment after last obstacle
        if (segStart < n) {
            val segResult = processSegment(line, positions, segStart, n - 1, idGenerator)
            for (k in segStart until n) {
                resultLine[k] = segResult.newLine[k]
            }
            movements.addAll(segResult.movements)
            merges.addAll(segResult.merges)
            totalScore += segResult.scoreGained
        }

        return LineResult(
            newLine = resultLine.toList(),
            movements = movements,
            merges = merges,
            scoreGained = totalScore
        )
    }

    private data class IndexedTile(val tile: Tile, val lineIndex: Int)

    private fun processSegment(
        line: List<Tile?>,
        positions: List<Position>,
        start: Int,
        end: Int,
        idGenerator: () -> Long
    ): LineResult {
        val nonEmpties = mutableListOf<IndexedTile>()
        for (idx in start..end) {
            val t = line[idx]
            if (t != null && !t.isObstacle && t.value > 0) {
                nonEmpties.add(IndexedTile(t, idx))
            }
        }

        val segResult = arrayOfNulls<Tile>(line.size)
        val movements = mutableListOf<TileMovement>()
        val merges = mutableListOf<TileMerge>()
        var scoreGained = 0

        var targetIdx = start
        var i = 0
        while (i < nonEmpties.size) {
            val current = nonEmpties[i]
            val next = if (i + 1 < nonEmpties.size) nonEmpties[i + 1] else null

            if (next != null && current.tile.value == next.tile.value) {
                val mergedValue = current.tile.value * 2
                val targetPos = positions[targetIdx]
                val resultingTile = Tile(id = idGenerator(), value = mergedValue, position = targetPos)

                if (current.lineIndex != targetIdx) {
                    movements.add(
                        TileMovement(
                            from = positions[current.lineIndex],
                            to = targetPos,
                            tileId = current.tile.id,
                            value = current.tile.value
                        )
                    )
                }
                movements.add(
                    TileMovement(
                        from = positions[next.lineIndex],
                        to = targetPos,
                        tileId = next.tile.id,
                        value = next.tile.value
                    )
                )

                merges.add(
                    TileMerge(
                        sourceTileIds = Pair(current.tile.id, next.tile.id),
                        resultingTile = resultingTile,
                        targetPosition = targetPos
                    )
                )

                segResult[targetIdx] = resultingTile
                scoreGained += mergedValue
                targetIdx++
                i += 2
            } else {
                val targetPos = positions[targetIdx]
                if (current.lineIndex != targetIdx) {
                    movements.add(
                        TileMovement(
                            from = positions[current.lineIndex],
                            to = targetPos,
                            tileId = current.tile.id,
                            value = current.tile.value
                        )
                    )
                }
                val movedTile = if (current.tile.position != targetPos) {
                    current.tile.copy(position = targetPos)
                } else {
                    current.tile
                }
                segResult[targetIdx] = movedTile
                targetIdx++
                i += 1
            }
        }

        return LineResult(
            newLine = segResult.toList(),
            movements = movements,
            merges = merges,
            scoreGained = scoreGained
        )
    }

    /**
     * Mathematical helper transforming an integer array towards index 0.
     * Values: 0 for empty, -1 for obstacle, > 0 for tile.
     * Returns Pair(resultingArray, scoreDelta).
     */
    fun compressAndMergeValues(values: List<Int>): Pair<List<Int>, Int> {
        var idCounter = 1L
        val tiles = values.mapIndexed { idx, v ->
            when (v) {
                0 -> null
                Tile.OBSTACLE_VALUE -> Tile.createObstacle(0, idx)
                else -> Tile(idCounter++, v, 0, idx)
            }
        }
        val result = compressAndMergeLine(tiles) { idCounter++ }
        val outValues = result.newLine.map { it?.value ?: 0 }
        return Pair(outValues, result.scoreGained)
    }
}
```

---

### 5.2 Randomness & Tile Identification (`RandomProvider`, `TileIdGenerator`)

```kotlin
package com.game2048.android.core.engine

import kotlin.random.Random

interface RandomProvider {
    fun nextInt(bound: Int): Int
    fun nextFloat(): Float
}

class DefaultRandomProvider(
    private val random: Random = Random.Default
) : RandomProvider {
    override fun nextInt(bound: Int): Int = random.nextInt(bound)
    override fun nextFloat(): Float = random.nextFloat()
}

class SeededRandomProvider(
    seed: Long
) : RandomProvider {
    private val random: Random = Random(seed)
    override fun nextInt(bound: Int): Int = random.nextInt(bound)
    override fun nextFloat(): Float = random.nextFloat()
}

class DeterministicRandomProvider(
    private val cellIndices: List<Int>,
    private val spawnProbabilities: List<Float>
) : RandomProvider {
    private var cellIndexPtr = 0
    private var probPtr = 0

    override fun nextInt(bound: Int): Int {
        val idx = cellIndices[cellIndexPtr % cellIndices.size]
        cellIndexPtr++
        return idx % bound
    }

    override fun nextFloat(): Float {
        val prob = spawnProbabilities[probPtr % spawnProbabilities.size]
        probPtr++
        return prob
    }
}
```

```kotlin
package com.game2048.android.core.engine

import java.util.concurrent.atomic.AtomicLong

interface TileIdGenerator {
    fun nextId(): Long
    fun reset(initialId: Long = 1L)
}

class AtomicTileIdGenerator(
    initialId: Long = 1L
) : TileIdGenerator {
    private val counter = AtomicLong(initialId)

    override fun nextId(): Long = counter.getAndIncrement()

    override fun reset(initialId: Long) {
        counter.set(initialId)
    }
}
```

---

### 5.3 `GridEngine.kt` (2D Board Orchestration)

`GridEngine` coordinates the full 2D board state:
1. Coordinates extraction of 1D lines for each swipe direction.
2. Invokes `LineMerger.compressAndMergeLine` on each line with explicit 2D coordinate projections.
3. Reconstructs the 2D grid matrix.
4. Checks mutation invariant (`moved = tileMovements.isNotEmpty() || tileMerges.isNotEmpty()`).
5. Spawns exactly 1 random tile if moved (90% chance of 2, 10% chance of 4).
6. Evaluates game-over and target-reached predicates in $O(R \times C)$ time.

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.MoveDirection
import com.game2048.android.core.model.MoveResult
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import com.game2048.android.core.model.TileMerge
import com.game2048.android.core.model.TileMovement

/**
 * 2D 2048 Engine executing directional moves, score accumulation, tile spawning, and state checks.
 */
class GridEngine(
    val grid: Grid,
    private val randomProvider: RandomProvider = DefaultRandomProvider(),
    private val idGenerator: TileIdGenerator = AtomicTileIdGenerator(),
    var targetTile: Int? = null
) {
    var score: Int = 0
        private set

    /**
     * Initializes the grid with [count] randomly spawned tiles (default 2).
     */
    fun spawnInitialTiles(count: Int = 2): List<Tile> {
        val spawned = mutableListOf<Tile>()
        repeat(count) {
            spawnRandomTile()?.let { spawned.add(it) }
        }
        return spawned
    }

    /**
     * Spawns a single tile into a uniformly chosen empty cell:
     * - 90% probability value = 2
     * - 10% probability value = 4
     */
    fun spawnRandomTile(): Tile? {
        val emptyCells = grid.getEmptyPositions()
        if (emptyCells.isEmpty()) return null

        val selectedIndex = randomProvider.nextInt(emptyCells.size)
        val targetPos = emptyCells[selectedIndex]
        val value = if (randomProvider.nextFloat() < SPAWN_4_PROBABILITY_THRESHOLD) 2 else 4
        val tile = Tile(id = idGenerator.nextId(), value = value, position = targetPos)
        grid.setTile(tile)
        return tile
    }

    /**
     * Executes a swipe in the given cardinal [direction].
     */
    fun move(direction: MoveDirection): MoveResult {
        val allMovements = mutableListOf<TileMovement>()
        val allMerges = mutableListOf<TileMerge>()
        var turnScore = 0

        when (direction) {
            MoveDirection.LEFT -> {
                for (r in 0 until grid.rows) {
                    val line = (0 until grid.cols).map { c -> grid[r, c] }
                    val positions = (0 until grid.cols).map { c -> Position(r, c) }
                    val result = LineMerger.compressAndMergeLine(line, positions) { idGenerator.nextId() }
                    for (c in 0 until grid.cols) {
                        grid.setTile(r, c, result.newLine[c])
                    }
                    allMovements.addAll(result.movements)
                    allMerges.addAll(result.merges)
                    turnScore += result.scoreGained
                }
            }
            MoveDirection.RIGHT -> {
                for (r in 0 until grid.rows) {
                    val line = (0 until grid.cols).map { c -> grid[r, grid.cols - 1 - c] }
                    val positions = (0 until grid.cols).map { c -> Position(r, grid.cols - 1 - c) }
                    val result = LineMerger.compressAndMergeLine(line, positions) { idGenerator.nextId() }
                    for (c in 0 until grid.cols) {
                        val pos = positions[c]
                        grid.setTile(pos.row, pos.col, result.newLine[c])
                    }
                    allMovements.addAll(result.movements)
                    allMerges.addAll(result.merges)
                    turnScore += result.scoreGained
                }
            }
            MoveDirection.UP -> {
                for (c in 0 until grid.cols) {
                    val line = (0 until grid.rows).map { r -> grid[r, c] }
                    val positions = (0 until grid.rows).map { r -> Position(r, c) }
                    val result = LineMerger.compressAndMergeLine(line, positions) { idGenerator.nextId() }
                    for (r in 0 until grid.rows) {
                        grid.setTile(r, c, result.newLine[r])
                    }
                    allMovements.addAll(result.movements)
                    allMerges.addAll(result.merges)
                    turnScore += result.scoreGained
                }
            }
            MoveDirection.DOWN -> {
                for (c in 0 until grid.cols) {
                    val line = (0 until grid.rows).map { r -> grid[grid.rows - 1 - r, c] }
                    val positions = (0 until grid.rows).map { r -> Position(grid.rows - 1 - r, c) }
                    val result = LineMerger.compressAndMergeLine(line, positions) { idGenerator.nextId() }
                    for (r in 0 until grid.rows) {
                        val pos = positions[r]
                        grid.setTile(pos.row, pos.col, result.newLine[r])
                    }
                    allMovements.addAll(result.movements)
                    allMerges.addAll(result.merges)
                    turnScore += result.scoreGained
                }
            }
        }

        val moved = allMovements.isNotEmpty() || allMerges.isNotEmpty()

        if (!moved) {
            return MoveResult.noMove(
                isGameOver = isGameOver(),
                isLevelWon = isLevelWon()
            )
        }

        score += turnScore
        val spawnedTile = spawnRandomTile()
        val gameOver = isGameOver()
        val levelWon = isLevelWon()

        return MoveResult(
            moved = true,
            scoreGained = turnScore,
            tileMovements = allMovements,
            tileMerges = allMerges,
            spawnedTile = spawnedTile,
            isGameOver = gameOver,
            isLevelWon = levelWon
        )
    }

    /**
     * Determines whether a move in the given direction is legal without mutating state.
     */
    fun canMove(direction: MoveDirection): Boolean {
        val dr = direction.deltaRow
        val dc = direction.deltaCol
        for (r in 0 until grid.rows) {
            for (c in 0 until grid.cols) {
                val v = grid.getValue(r, c)
                if (v <= 0) continue // Empty or obstacle cell cannot initiate a move
                val nr = r + dr
                val nc = c + dc
                if (grid.isWithinBounds(nr, nc)) {
                    val nv = grid.getValue(nr, nc)
                    if (nv == 0 || nv == v) {
                        return true
                    }
                }
            }
        }
        return false
    }

    /**
     * Fast O(RC) game over evaluation:
     * Game is over iff no legal moves exist in any of the 4 directions.
     */
    fun isGameOver(): Boolean = MoveDirection.entries.none { canMove(it) }

    /**
     * Evaluates whether current board contains any tile reaching or exceeding [targetTile].
     */
    fun isLevelWon(): Boolean {
        val target = targetTile ?: return false
        return grid.getAllTiles().any { it.value >= target }
    }

    /**
     * Resets the game board and score.
     */
    fun reset(initialObstacles: Set<Position> = grid.obstacles, spawnInitial: Boolean = true) {
        score = 0
        for (r in 0 until grid.rows) {
            for (c in 0 until grid.cols) {
                val pos = Position(r, c)
                if (pos in initialObstacles) {
                    grid.setTile(Tile.createObstacle(pos))
                } else {
                    grid.clearCell(r, c)
                }
            }
        }
        if (spawnInitial) {
            spawnInitialTiles(2)
        }
    }

    companion object {
        const val SPAWN_4_PROBABILITY_THRESHOLD = 0.90f
    }
}
```

---

## 6. Merge Truth Table & Exhaustive Edge Cases

| Scenario | Input Array (sliding LEFT) | Expected Output Array | Merges Count | Score Delta | Rationale / Invariant Verified |
|:---:|:---|:---|:---:|:---:|:---|
| 1 | `[2, 2, 4, 4]` | `[4, 8, 0, 0]` | 2 | $+12$ | Both pairs merge independently in single pass. |
| 2 | `[2, 2, 2, 0]` | `[4, 2, 0, 0]` | 1 | $+4$ | Left pair merges; 3rd tile cannot double-merge into 4. |
| 3 | `[2, 2, 2, 2]` | `[4, 4, 0, 0]` | 2 | $+8$ | Two distinct pairs merge; neither merges into 8. |
| 4 | `[4, 2, 2, 0]` | `[4, 4, 0, 0]` | 1 | $+4$ | Trailing pair merges to 4; does not merge into leading 4. |
| 5 | `[2, 0, 2, 4]` | `[4, 4, 0, 0]` | 1 | $+4$ | Gaps collapse, identical pair merges, trailing tile slides. |
| 6 | `[0, 2, 0, 2]` | `[4, 0, 0, 0]` | 1 | $+4$ | Both empty spaces collapse, identical tiles merge. |
| 7 | `[2, 4, 2, 4]` | `[2, 4, 2, 4]` | 0 | $+0$ | Alternating values; no movement, no score change. |
| 8 | `[0, 0, 0, 0]` | `[0, 0, 0, 0]` | 0 | $+0$ | Entirely empty line; idempotent no-op. |
| 9 | `[0, 0, 2, 0]` | `[2, 0, 0, 0]` | 0 | $+0$ | Pure slide without merge; score delta 0. |
| 10 | `[8, 4, 2, 2]` | `[8, 4, 4, 0]` | 1 | $+4$ | Only trailing pair merges. |
| 11 | `[2, 2, 4, 8]` | `[4, 4, 8, 0]` | 1 | $+4$ | Only leading pair merges. |
| 12 | `[2, 2, -1, 4, 4]` | `[4, 0, -1, 8, 0]` | 2 | $+12$ | Obstacle partitions row into independent sub-domains. |
| 13 | `[-1, 2, 2, 0]` | `[-1, 4, 0, 0]` | 1 | $+4$ | Obstacle at index 0 remains fixed; remaining cells merge. |
| 14 | `[2, 2, 0, -1]` | `[4, 0, 0, -1]` | 1 | $+4$ | Obstacle at line end remains fixed; leading cells merge. |
| 15 | `[2, 0, -1, 0, 2]` | `[2, 0, -1, 2, 0]` | 0 | $+0$ | Tiles cannot cross obstacle boundary. |
| 16 | `[0, 2, 2, -1]` | `[4, 0, 0, -1]` | 1 | $+4$ | Tiles slide and merge against obstacle boundary. |
| 17 | `[2, -1, 2, -1, 2]` | `[2, -1, 2, -1, 2]` | 0 | $+0$ | Multiple obstacles create 1-cell isolated pockets. |

---

## 7. JUnit 4 Unit Test Suite Blueprint (`src/test/java`)

The following test suites must be created under `android_2048_game/app/src/test/java/com/game2048/android`:

### 7.1 `core/engine/LineMergerTest.kt`
Covers 100% of 1D merge truth tables, non-double-merge invariants, and obstacle boundaries.

```kotlin
package com.game2048.android.core.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LineMergerTest {

    @Test
    fun testEmptyLineRemainsEmpty() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(0, 0, 0, 0))
        assertEquals(listOf(0, 0, 0, 0), result)
        assertEquals(0, score)
    }

    @Test
    fun testSingleTileSlidesToEdge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(0, 0, 2, 0))
        assertEquals(listOf(2, 0, 0, 0), result)
        assertEquals(0, score)
    }

    @Test
    fun testSingleTileAlreadyAtEdge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 0, 0, 0))
        assertEquals(listOf(2, 0, 0, 0), result)
        assertEquals(0, score)
    }

    @Test
    fun testTwoIdenticalTilesMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, 0, 0))
        assertEquals(listOf(4, 0, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testTwoDifferentTilesDoNotMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 4, 0, 0))
        assertEquals(listOf(2, 4, 0, 0), result)
        assertEquals(0, score)
    }

    @Test
    fun testTwoIdenticalTilesWithGapMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 0, 2, 0))
        assertEquals(listOf(4, 0, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testTwoIdenticalTilesAtOppositeEndsMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 0, 0, 2))
        assertEquals(listOf(4, 0, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testFourIdenticalTilesMergeInPairsNoQuadrupleMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, 2, 2))
        assertEquals(listOf(4, 4, 0, 0), result)
        assertEquals(8, score)
    }

    @Test
    fun testThreeIdenticalTilesMergeLeadingPair() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, 2, 0))
        assertEquals(listOf(4, 2, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testThreeIdenticalTilesTrailingPairMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(0, 2, 2, 2))
        assertEquals(listOf(4, 2, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testPairAfterSingleTileMergesWithoutDoubleMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(4, 2, 2, 0))
        assertEquals(listOf(4, 4, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testTwoPairsMergeIndependently() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, 4, 4))
        assertEquals(listOf(4, 8, 0, 0), result)
        assertEquals(12, score)
    }

    @Test
    fun testMultipleMergesWithGaps() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 0, 2, 4))
        assertEquals(listOf(4, 4, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testTrailingPairMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(8, 4, 2, 2))
        assertEquals(listOf(8, 4, 4, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testLeadingPairMerge() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, 4, 8))
        assertEquals(listOf(4, 4, 8, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testObstacleSplitsMergeDomain() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, -1, 4, 4))
        assertEquals(listOf(4, 0, -1, 8, 0), result)
        assertEquals(12, score)
    }

    @Test
    fun testObstacleAtStart() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(-1, 2, 2, 0))
        assertEquals(listOf(-1, 4, 0, 0), result)
        assertEquals(4, score)
    }

    @Test
    fun testObstacleAtEnd() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 2, 0, -1))
        assertEquals(listOf(4, 0, 0, -1), result)
        assertEquals(4, score)
    }

    @Test
    fun testTilesCannotCrossObstacle() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, 0, -1, 0, 2))
        assertEquals(listOf(2, 0, -1, 2, 0), result)
        assertEquals(0, score)
    }

    @Test
    fun testMultipleObstaclesInLine() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(2, -1, 2, -1, 2))
        assertEquals(listOf(2, -1, 2, -1, 2), result)
        assertEquals(0, score)
    }

    @Test
    fun testSlideAndMergeAgainstObstacle() {
        val (result, score) = LineMerger.compressAndMergeValues(listOf(0, 2, 2, -1))
        assertEquals(listOf(4, 0, 0, -1), result)
        assertEquals(4, score)
    }
}
```

---

### 7.2 `core/model/GridModelTest.kt`
Covers arbitrary dimensions (3x3, 4x4, 5x5), bounds checking, obstacle immutability, deep copy, and equality.

```kotlin
package com.game2048.android.core.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GridModelTest {

    @Test
    fun testStandardDimensionsSupported() {
        val g3x3 = Grid(3, 3)
        assertEquals(3, g3x3.rows)
        assertEquals(3, g3x3.cols)
        assertEquals(9, g3x3.getEmptyPositions().size)

        val g4x4 = Grid(4, 4)
        assertEquals(4, g4x4.rows)
        assertEquals(4, g4x4.cols)
        assertEquals(16, g4x4.getEmptyPositions().size)

        val g5x5 = Grid(5, 5)
        assertEquals(5, g5x5.rows)
        assertEquals(5, g5x5.cols)
        assertEquals(25, g5x5.getEmptyPositions().size)
    }

    @Test(expected = IllegalArgumentException::class)
    fun testDimensionsLessThanTwoRejected() {
        Grid(1, 4)
    }

    @Test(expected = IllegalArgumentException::class)
    fun testDimensionsGreaterThanEightRejected() {
        Grid(9, 4)
    }

    @Test
    fun testObstacleCellInitialization() {
        val obstacles = setOf(Position(1, 1), Position(2, 2))
        val grid = Grid(4, 4, obstacles)

        assertTrue(grid.isObstacle(1, 1))
        assertTrue(grid.isObstacle(2, 2))
        assertEquals(-1, grid.getValue(1, 1))
        assertEquals(-1, grid.getValue(2, 2))
        assertFalse(grid.isEmpty(1, 1))

        // Total empty positions should be 16 - 2 = 14
        assertEquals(14, grid.getEmptyPositions().size)
    }

    @Test(expected = IllegalArgumentException::class)
    fun testCannotOverwriteObstacleWithRegularTile() {
        val obstacles = setOf(Position(0, 0))
        val grid = Grid(4, 4, obstacles)
        grid.setTile(0, 0, Tile(1L, 2, 0, 0))
    }

    @Test
    fun testDeepCopyIndependence() {
        val grid = Grid(4, 4, setOf(Position(1, 1)))
        grid.setTile(Tile(10L, 4, 0, 0))

        val copy = grid.copy()
        assertEquals(grid, copy)

        // Mutate original
        grid.setTile(Tile(11L, 8, 0, 1))
        assertNotEquals(grid, copy)
        assertEquals(0, copy.getValue(0, 1))
        assertEquals(8, grid.getValue(0, 1))
    }
}
```

---

### 7.3 `core/engine/GridEngineTest.kt`
Covers full 2D directional moves, score accumulation, deterministic spawning, game-over evaluation, and level win condition.

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.MoveDirection
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GridEngineTest {

    @Test
    fun testSwipeLeftMergesAndAccumulatesScore() {
        val matrix = arrayOf(
            intArrayOf(2, 2, 0, 0),
            intArrayOf(4, 0, 4, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(2, 2, 2, 2)
        )
        val grid = Grid.fromValues(matrix)
        val deterministicPrng = DeterministicRandomProvider(listOf(0), listOf(0.5f))
        val engine = GridEngine(grid, deterministicPrng)

        val result = engine.move(MoveDirection.LEFT)
        assertTrue(result.moved)
        assertEquals(4 + 8 + 8, result.scoreGained)
        assertEquals(20, engine.score)

        assertEquals(4, grid.getValue(0, 0))
        assertEquals(8, grid.getValue(1, 0))
        assertEquals(4, grid.getValue(3, 0))
        assertEquals(4, grid.getValue(3, 1))
    }

    @Test
    fun testSwipeRightTranslatesTowardsRightBoundary() {
        val matrix = arrayOf(
            intArrayOf(2, 0, 2, 4),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0)
        )
        val grid = Grid.fromValues(matrix)
        val deterministicPrng = DeterministicRandomProvider(listOf(0), listOf(0.5f))
        val engine = GridEngine(grid, deterministicPrng)

        val result = engine.move(MoveDirection.RIGHT)
        assertTrue(result.moved)
        assertEquals(4, result.scoreGained)
        assertEquals(4, grid.getValue(0, 3)) // pre-existing 4
        assertEquals(4, grid.getValue(0, 2)) // merged (2, 2)
    }

    @Test
    fun testSwipeUpTranslatesTowardsTopBoundary() {
        val matrix = arrayOf(
            intArrayOf(0, 0, 0, 0),
            intArrayOf(2, 0, 0, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(2, 0, 0, 0)
        )
        val grid = Grid.fromValues(matrix)
        val engine = GridEngine(grid, DeterministicRandomProvider(listOf(0), listOf(0.5f)))

        val result = engine.move(MoveDirection.UP)
        assertTrue(result.moved)
        assertEquals(4, result.scoreGained)
        assertEquals(4, grid.getValue(0, 0))
    }

    @Test
    fun testSwipeDownTranslatesTowardsBottomBoundary() {
        val matrix = arrayOf(
            intArrayOf(2, 0, 0, 0),
            intArrayOf(2, 0, 0, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0)
        )
        val grid = Grid.fromValues(matrix)
        val engine = GridEngine(grid, DeterministicRandomProvider(listOf(0), listOf(0.5f)))

        val result = engine.move(MoveDirection.DOWN)
        assertTrue(result.moved)
        assertEquals(4, result.scoreGained)
        assertEquals(4, grid.getValue(3, 0))
    }

    @Test
    fun testInvalidMoveDoesNotMutateGridOrSpawnTile() {
        val matrix = arrayOf(
            intArrayOf(2, 4, 8, 16),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0)
        )
        val grid = Grid.fromValues(matrix)
        val engine = GridEngine(grid)

        val result = engine.move(MoveDirection.UP)
        assertFalse(result.moved)
        assertEquals(0, result.scoreGained)
        assertNull(result.spawnedTile)
        assertEquals(0, engine.score)
    }

    @Test
    fun testGameOverDetectionFullGridNoMoves() {
        val matrix = arrayOf(
            intArrayOf(2, 4, 2, 4),
            intArrayOf(4, 2, 4, 2),
            intArrayOf(2, 4, 2, 4),
            intArrayOf(4, 2, 4, 2)
        )
        val grid = Grid.fromValues(matrix)
        val engine = GridEngine(grid)

        assertTrue(engine.isGameOver())
        assertFalse(engine.canMove(MoveDirection.UP))
        assertFalse(engine.canMove(MoveDirection.DOWN))
        assertFalse(engine.canMove(MoveDirection.LEFT))
        assertFalse(engine.canMove(MoveDirection.RIGHT))
    }

    @Test
    fun testGameOverDetectionFullGridWithAvailableMove() {
        val matrix = arrayOf(
            intArrayOf(2, 4, 2, 4),
            intArrayOf(4, 2, 4, 2),
            intArrayOf(2, 4, 2, 4),
            intArrayOf(4, 2, 4, 4) // pair (4, 4) at end of row 3
        )
        val grid = Grid.fromValues(matrix)
        val engine = GridEngine(grid)

        assertFalse(engine.isGameOver())
        assertTrue(engine.canMove(MoveDirection.LEFT) || engine.canMove(MoveDirection.RIGHT))
    }

    @Test
    fun testLevelWonDetection() {
        val matrix = arrayOf(
            intArrayOf(1024, 1024, 0, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0),
            intArrayOf(0, 0, 0, 0)
        )
        val grid = Grid.fromValues(matrix)
        val engine = GridEngine(grid, DeterministicRandomProvider(listOf(0), listOf(0.5f)))
        engine.targetTile = 2048

        assertFalse(engine.isLevelWon())
        val result = engine.move(MoveDirection.LEFT)
        assertTrue(result.moved)
        assertEquals(2048, grid.getValue(0, 0))
        assertTrue(result.isLevelWon)
        assertTrue(engine.isLevelWon())
    }

    @Test
    fun testObstacleGridMovementsAndGameContinuity() {
        val obstacles = setOf(Position(1, 1), Position(2, 2))
        val grid = Grid(4, 4, obstacles)
        grid.setTile(Tile(1L, 2, 1, 0))
        grid.setTile(Tile(2L, 2, 1, 2))
        val engine = GridEngine(grid, DeterministicRandomProvider(listOf(0), listOf(0.5f)))

        // Swiping RIGHT: tile at (1,0) should stop before obstacle at (1,1)
        val result = engine.move(MoveDirection.RIGHT)
        assertTrue(result.moved)
        assertEquals(2, grid.getValue(1, 0)) // blocked by (1,1) obstacle
        assertEquals(2, grid.getValue(1, 3)) // tile from (1,2) slides right to (1,3)
    }
}
```

---

## 8. Verification Strategy & Implementation Protocol

When Milestone 2 implementation begins, the implementer agent should follow this exact sequence:

1. **Verify Scaffolding & JVM Test Harness**:
   Execute `gradlew.bat testDebugUnitTest` to ensure baseline smoke tests pass cleanly.
2. **Implement Models**:
   Create the 7 data models in `com.game2048.android.core.model`:
   `Position.kt`, `MoveDirection.kt`, `Tile.kt`, `Grid.kt`, `TileMovement.kt`, `TileMerge.kt`, `MoveResult.kt`.
3. **Implement Engines**:
   Create the engine components in `com.game2048.android.core.engine`:
   `RandomProvider.kt`, `TileIdGenerator.kt`, `LineMerger.kt`, `GridEngine.kt`.
4. **Implement Unit Tests**:
   Create the test classes in `app/src/test/java/com/game2048/android`:
   `core/model/GridModelTest.kt`, `core/engine/LineMergerTest.kt`, `core/engine/GridEngineTest.kt`.
5. **Execute Test Suite**:
   Run `.\gradlew.bat testDebugUnitTest --info`.
   Verify 100% of tests pass in pure headless JVM in < 1 second.
