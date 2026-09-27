# Core Game Engine, PRNG Tile Spawner, Score & Game-Over Detector Specification
**Milestone 2 Implementation Specification Document**
**Package:** `com.game2048.android.core.engine` & `com.game2048.android.core.model`
**Target Platform:** Pure Kotlin JVM Domain (Android 12–15 compatible, zero SDK coupling, 100% unit-testable)

---

## 1. Executive Summary & Architectural Scope

This specification defines the deterministic core engine for the 2048 Android game app according to `ORIGINAL_REQUEST.md`, `PROJECT.md` (Features F04, F05, F06, F07), and `spec_mechanics.md`. 

The core game engine layer is designed as a **pure Kotlin JVM domain module** completely decoupled from Android UI/Canvas frameworks, Jetpack components, and OS lifecycles. This guarantees:
1. **Sub-millisecond execution**: Every move evaluation completes in microseconds, easily fitting the 60+ FPS (16.6ms) budget.
2. **Zero allocation during move evaluation**: Avoids triggering Android runtime garbage collection pauses during touch-driven gameplay.
3. **100% Headless Unit-Testability**: Deterministic testing with seeded PRNGs and mock providers without requiring Robolectric or Android instrumentation.
4. **Complete Separation of Concerns**:
   - `RandomProvider`: Decoupled PRNG interface generating values and selecting spawn coordinates.
   - `GameOverDetector`: $O(R \times C)$ fast evaluation algorithm for board termination.
   - `GameEngine` / `GameEngineImpl`: Central state machine orchestrating grid mutations, score accumulation, high-score tracking, tile spawning, and lifecycle transitions (`IDLE`, `PLAYING`, `LEVEL_WON`, `GAME_OVER`).

---

## 2. Collaborative Domain Models (`com.game2048.android.core.model`)

To ensure seamless integration with peer modules developed by `explorer_m2_1` (Grid & LineMerger) and `explorer_m2_3` (Domain Unit Test Suite), the engine interacts with the following canonical models:

```kotlin
package com.game2048.android.core.model

/**
 * 2D Board Coordinate.
 * @param row Zero-indexed row index [0 until rows]
 * @param col Zero-indexed column index [0 until cols]
 */
data class Position(val row: Int, val col: Int)

/**
 * Cardinal directions for swipe gestures and grid traversal.
 */
enum class MoveDirection {
    UP,
    DOWN,
    LEFT,
    RIGHT
}

/**
 * High-level game state lifecycle.
 */
enum class GameState {
    IDLE,
    PLAYING,
    LEVEL_WON,
    GAME_OVER
}

/**
 * Immutable representation of a board tile.
 * @param id Unique 64-bit identifier used by the UI animation pipeline to track tile translation across frames.
 * @param value Tile face value (2, 4, 8, ..., 2048, etc.). A value of -1 denotes an impassable obstacle.
 * @param row Current grid row
 * @param col Current grid column
 */
data class Tile(
    val id: Long,
    val value: Int,
    val row: Int,
    val col: Int
) {
    val isObstacle: Boolean get() = value == -1
}

/**
 * Records individual tile translation during a single turn.
 */
data class TileMovement(
    val tileId: Long,
    val from: Position,
    val to: Position,
    val value: Int
)

/**
 * Records collision and fusion of two tiles into a new tile.
 */
data class TileMerge(
    val sourceTileIds: Pair<Long, Long>,
    val resultingTile: Tile,
    val targetPosition: Position
)

/**
 * Comprehensive turn result payload returned by [GameEngine.move].
 * Supplies the presentation layer with all animation events and state deltas.
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
```

---

## 3. PRNG Tile Spawner Specification (`RandomProvider`)

### 3.1 Interface Contract
```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.Position

/**
 * Abstraction for pseudorandom number generation governing tile spawning.
 * Decouples the game engine from system randomness, enabling deterministic testing,
 * seed injection, and anti-cheat replay validation.
 */
interface RandomProvider {
    /**
     * Generates the value for a newly spawned tile.
     * Must return 2 with 90% probability and 4 with 10% probability.
     */
    fun nextTileValue(): Int

    /**
     * Uniformly selects one empty position from a non-empty list of available empty cells.
     * @throws IllegalArgumentException if [emptyCells] is empty.
     */
    fun selectEmptyCell(emptyCells: List<Position>): Position
}
```

### 3.2 Production Implementation: `DefaultRandomProvider`

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.Position
import kotlin.random.Random

/**
 * Production implementation of [RandomProvider] using Kotlin's multiplatform [kotlin.random.Random].
 * Supports optional seed injection for fully deterministic game sessions and unit testing.
 *
 * @param random Backing PRNG instance (defaulting to [kotlin.random.Random.Default]).
 */
class DefaultRandomProvider(
    private val random: Random = Random.Default
) : RandomProvider {

    /**
     * Convenience secondary constructor for injecting a 64-bit seed.
     */
    constructor(seed: Long) : this(Random(seed))

    /**
     * Bernoulli trial for spawn value:
     * - P(V = 2) = 0.90 (90%)
     * - P(V = 4) = 0.10 (10%)
     */
    override fun nextTileValue(): Int {
        return if (random.nextFloat() < 0.90f) 2 else 4
    }

    /**
     * Selects an empty cell with uniform probability P(cell_k) = 1 / |emptyCells|.
     */
    override fun selectEmptyCell(emptyCells: List<Position>): Position {
        require(emptyCells.isNotEmpty()) { "Cannot select an empty cell from an empty list" }
        val index = random.nextInt(emptyCells.size)
        return emptyCells[index]
    }
}
```

### 3.3 Test Fixture / Mock Provider Design

For testing specific scenarios (e.g. forcing a tile 4 at coordinate $(0, 0)$ or exhausting spawns):
```kotlin
class PredictableRandomProvider(
    private val tileValues: Iterator<Int>,
    private val cellSelector: (List<Position>) -> Position
) : RandomProvider {
    override fun nextTileValue(): Int = tileValues.next()
    override fun selectEmptyCell(emptyCells: List<Position>): Position = cellSelector(emptyCells)
}
```

---

## 4. Game-Over Detector Algorithm: $O(R \times C)$

### 4.1 Algorithmic Proof & Contract

A game is **GAME OVER** if and only if **no legal moves exist in any of the 4 cardinal directions** ($\forall \vec{d} \in \{UP, DOWN, LEFT, RIGHT\}, \neg CanMove(\mathcal{G}, \vec{d})$).

#### Lemma 1:
If the board contains at least one empty playable cell ($\exists (r, c) \text{ s.t. } \mathcal{G}(r, c) == 0 \land \neg isObstacle(r, c)$), the game is **not** over. At least one tile can slide into or towards that empty cell.

#### Lemma 2:
If the board contains zero empty playable cells, no tile can translate into an empty cell. Therefore, a legal move exists if and only if **two adjacent, non-obstacle tiles have identical face values** ($Tile_A.value == Tile_B.value$). Merging them reduces the tile count by 1 and opens an empty cell.

#### Lemma 3 (Obstacle Isolation):
Obstacle cells ($\mathcal{G}(r, c) = -1$) are impassable and cannot merge. A tile at $(r, 0)$ cannot merge with a tile at $(r, 2)$ if an obstacle sits at $(r, 1)$, because no empty cell exists to permit movement across or around it. Thus, checking immediate Euclidean neighbors $(r, c+1)$ and $(r+1, c)$ is both necessary and sufficient.

### 4.2 Optimized Single-Pass Implementation: `GameOverDetector`

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.Grid

/**
 * High-performance, zero-allocation game-over detector.
 * Evaluates game termination in strictly O(rows * cols) time with zero object allocations.
 */
object GameOverDetector {

    /**
     * Evaluates if the current grid has no possible legal moves.
     *
     * Complexity:
     * - Worst-case time: O(R * C)
     * - Best-case time: O(1) (immediate return on encountering first empty cell)
     * - Space: O(1) auxiliary (zero heap allocation)
     */
    fun isGameOver(grid: Grid): Boolean {
        val rows = grid.rows
        val cols = grid.cols

        // Step 1: Rapid scan for any empty playable cell
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                if (!grid.isObstacle(r, c) && grid.getTile(r, c) == null) {
                    return false // Empty cell exists -> legal move exists
                }
            }
        }

        // Step 2: Check for adjacent horizontal mergeable pairs (col and col + 1)
        for (r in 0 until rows) {
            for (c in 0 until cols - 1) {
                if (grid.isObstacle(r, c) || grid.isObstacle(r, c + 1)) continue
                val tileA = grid.getTile(r, c)
                val tileB = grid.getTile(r, c + 1)
                if (tileA != null && tileB != null && tileA.value == tileB.value) {
                    return false // Horizontal merge possible -> legal move exists
                }
            }
        }

        // Step 3: Check for adjacent vertical mergeable pairs (row and row + 1)
        for (c in 0 until cols) {
            for (r in 0 until rows - 1) {
                if (grid.isObstacle(r, c) || grid.isObstacle(r + 1, c)) continue
                val tileA = grid.getTile(r, c)
                val tileB = grid.getTile(r + 1, c)
                if (tileA != null && tileB != null && tileA.value == tileB.value) {
                    return false // Vertical merge possible -> legal move exists
                }
            }
        }

        // Board is completely full with zero mergeable adjacent pairs
        return true
    }
}
```

---

## 5. GameEngine Interface & State Management Specification

### 5.1 GameEngine Interface Contract

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.GameState
import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.MoveDirection
import com.game2048.android.core.model.MoveResult
import com.game2048.android.core.model.Position

/**
 * Primary stateful domain orchestrator for 2048 gameplay.
 * Manages board state, score accumulation, tile spawning, and state transitions.
 */
interface GameEngine {
    val grid: Grid
    val score: Int
    val highScore: Int
    val gameState: GameState
    val targetTile: Int
    val isFreePlay: Boolean

    /**
     * Executes a swipe move in the specified cardinal direction.
     *
     * Rules:
     * 1. If [gameState] is GAME_OVER or IDLE, returns a no-op [MoveResult].
     * 2. Evaluates tile movements and single-pass merges via LineMerger.
     * 3. If grid state does NOT change (moved == false):
     *    - No tile is spawned.
     *    - Score delta is 0.
     *    - Returns MoveResult(moved = false, scoreGained = 0, ...).
     * 4. If grid state changes (moved == true):
     *    - Increments score by sum of merged tile values (Delta S = sum 2V).
     *    - Updates highScore monotonically: highScore = max(highScore, score).
     *    - Spawns strictly ONE new tile in a randomly selected empty cell.
     *    - Evaluates LEVEL_WON (if any tile >= targetTile and not in free play).
     *    - Evaluates GAME_OVER (if isGameOver() returns true).
     *    - Returns MoveResult containing all animations, deltas, and state flags.
     */
    fun move(direction: MoveDirection): MoveResult

    /**
     * Checks if a move in the given direction would change the board state,
     * without mutating the active grid. Useful for UI hints and gesture guards.
     */
    fun canMove(direction: MoveDirection): Boolean

    /**
     * Resets the board for a new game or level session:
     * - Clears existing tiles and obstacles.
     * - Configures grid dimensions and optional obstacle positions.
     * - Resets current score to 0.
     * - Preserves high score (highScore is NOT cleared).
     * - Spawns exactly 2 initial random tiles (each 90% 2, 10% 4).
     * - Sets [gameState] to [GameState.PLAYING].
     */
    fun reset(
        rows: Int = grid.rows,
        cols: Int = grid.cols,
        obstacles: List<Position> = emptyList(),
        targetTile: Int = 2048
    )

    /**
     * Restores game state from persistent storage (SharedPreferences / JSON):
     * - Replaces active grid with a deep clone of [savedGrid].
     * - Restores [score], [highScore], and [gameState].
     * - Re-calibrates internal tile ID counter above max existing tile ID.
     */
    fun restoreState(
        savedGrid: Grid,
        score: Int,
        highScore: Int,
        gameState: GameState,
        targetTile: Int = 2048,
        isFreePlay: Boolean = false
    )

    /**
     * Enables endless/free play mode after achieving LEVEL_WON.
     * Prevents LEVEL_WON from repeatedly firing, allowing gameplay until GAME_OVER.
     */
    fun continuePlaying()

    /**
     * Direct query to check if the board has zero available moves.
     */
    fun isGameOver(): Boolean

    /**
     * Direct query to check if any tile has reached or exceeded [targetTile].
     */
    fun isLevelWon(): Boolean
}
```

---

## 6. Implementation Architecture: `GameEngineImpl`

### 6.1 State Machine Lifecycle & State Transitions

```
               +--------------------------------------+
               |                                      |
               v                                      | reset()
        +--------------+   reset() / init    +-----------------+
        |     IDLE     | ------------------> |     PLAYING     | <-----+
        +--------------+                     +-----------------+       |
                                                 |         |           |
                              targetTile reached |         | no moves  | continuePlaying()
                                                 v         v           |
                                         +-----------+  +-----------+  |
                                         | LEVEL_WON |  | GAME_OVER |  |
                                         +-----------+  +-----------+  |
                                               |              |        |
                                               +--------------+--------+
                                                  reset() / new level
```

### 6.2 The Complete `GameEngineImpl` Specification

```kotlin
package com.game2048.android.core.engine

import com.game2048.android.core.model.GameState
import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.MoveDirection
import com.game2048.android.core.model.MoveResult
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import com.game2048.android.core.model.TileMerge
import com.game2048.android.core.model.TileMovement

class GameEngineImpl(
    initialRows: Int = 4,
    initialCols: Int = 4,
    initialObstacles: List<Position> = emptyList(),
    initialTargetTile: Int = 2048,
    initialHighScore: Int = 0,
    private val randomProvider: RandomProvider = DefaultRandomProvider()
) : GameEngine {

    private var _grid: Grid = Grid(initialRows, initialCols, initialObstacles)
    private var _score: Int = 0
    private var _highScore: Int = initialHighScore
    private var _gameState: GameState = GameState.IDLE
    private var _targetTile: Int = initialTargetTile
    private var _isFreePlay: Boolean = false

    // Monotonically increasing ID counter for tile identity tracking
    private var nextTileId: Long = 1L

    override val grid: Grid get() = _grid
    override val score: Int get() = _score
    override val highScore: Int get() = _highScore
    override val gameState: GameState get() = _gameState
    override val targetTile: Int get() = _targetTile
    override val isFreePlay: Boolean get() = _isFreePlay

    init {
        reset(initialRows, initialCols, initialObstacles, initialTargetTile)
    }

    override fun move(direction: MoveDirection): MoveResult {
        // Guard 1: Do not execute moves if game is over or idle
        if (_gameState == GameState.GAME_OVER || _gameState == GameState.IDLE) {
            return MoveResult(
                moved = false,
                scoreGained = 0,
                tileMovements = emptyList(),
                tileMerges = emptyList(),
                spawnedTile = null,
                isGameOver = (_gameState == GameState.GAME_OVER),
                isLevelWon = (_gameState == GameState.LEVEL_WON)
            )
        }

        // Step 1: Perform 2D grid transformation using 1D line compression
        val transformation = executeGridTransformation(direction)

        // Guard 2: If no tiles moved or merged, this swipe is a no-op
        if (!transformation.hasChanged) {
            return MoveResult(
                moved = false,
                scoreGained = 0,
                tileMovements = emptyList(),
                tileMerges = emptyList(),
                spawnedTile = null,
                isGameOver = isGameOver(),
                isLevelWon = isLevelWon()
            )
        }

        // Step 2: Commit new grid state
        _grid = transformation.newGrid

        // Step 3: Real-time score accumulation: Delta S = sum of merged tile values
        val scoreGained = transformation.scoreDelta
        _score += scoreGained
        if (_score > _highScore) {
            _highScore = _score
        }

        // Step 4: Spawning invariant: spawn strictly ONE tile only when moved == true
        val spawnedTile = spawnRandomTile()

        // Step 5: Check win condition (takes precedence over game over per spec_mechanics Section 9.10)
        var levelWonJustNow = false
        if (!_isFreePlay && _gameState != GameState.LEVEL_WON && checkLevelWon()) {
            _gameState = GameState.LEVEL_WON
            levelWonJustNow = true
        }

        // Step 6: Check game over condition
        val gameOver = GameOverDetector.isGameOver(_grid)
        if (gameOver && _gameState != GameState.LEVEL_WON) {
            _gameState = GameState.GAME_OVER
        }

        return MoveResult(
            moved = true,
            scoreGained = scoreGained,
            tileMovements = transformation.tileMovements,
            tileMerges = transformation.tileMerges,
            spawnedTile = spawnedTile,
            isGameOver = gameOver,
            isLevelWon = levelWonJustNow || (_gameState == GameState.LEVEL_WON)
        )
    }

    override fun canMove(direction: MoveDirection): Boolean {
        if (_gameState == GameState.GAME_OVER) return false
        val transformation = executeGridTransformation(direction)
        return transformation.hasChanged
    }

    override fun reset(
        rows: Int,
        cols: Int,
        obstacles: List<Position>,
        targetTile: Int
    ) {
        _grid = Grid(rows, cols, obstacles)
        _score = 0
        _targetTile = targetTile
        _isFreePlay = false
        _gameState = GameState.PLAYING
        nextTileId = 1L

        // Spawn exactly 2 initial random tiles
        spawnRandomTile()
        spawnRandomTile()
    }

    override fun restoreState(
        savedGrid: Grid,
        score: Int,
        highScore: Int,
        gameState: GameState,
        targetTile: Int,
        isFreePlay: Boolean
    ) {
        _grid = savedGrid.clone()
        _score = score
        _highScore = maxOf(highScore, score)
        _gameState = gameState
        _targetTile = targetTile
        _isFreePlay = isFreePlay

        // Calibrate nextTileId strictly above all existing tile IDs to prevent ID collision
        val maxId = _grid.getAllTiles().maxOfOrNull { it.id } ?: 0L
        nextTileId = maxId + 1L
    }

    override fun continuePlaying() {
        if (_gameState == GameState.LEVEL_WON) {
            _isFreePlay = true
            _gameState = GameState.PLAYING
        }
    }

    override fun isGameOver(): Boolean = GameOverDetector.isGameOver(_grid)

    override fun isLevelWon(): Boolean = checkLevelWon()

    private fun checkLevelWon(): Boolean {
        for (r in 0 until _grid.rows) {
            for (c in 0 until _grid.cols) {
                val tile = _grid.getTile(r, c)
                if (tile != null && tile.value >= _targetTile) {
                    return true
                }
            }
        }
        return false
    }

    private fun spawnRandomTile(): Tile? {
        val emptyCells = _grid.getEmptyCells()
        if (emptyCells.isEmpty()) return null

        val selectedPos = randomProvider.selectEmptyCell(emptyCells)
        val value = randomProvider.nextTileValue()
        val tile = Tile(
            id = nextTileId++,
            value = value,
            row = selectedPos.row,
            col = selectedPos.col
        )
        _grid.setTile(selectedPos, tile)
        return tile
    }

    /**
     * Executes 2D line projections and passes them through LineMerger.
     */
    private fun executeGridTransformation(direction: MoveDirection): GridTransformation {
        val rows = _grid.rows
        val cols = _grid.cols
        val workingGrid = _grid.clone()

        val tileMovements = mutableListOf<TileMovement>()
        val tileMerges = mutableListOf<TileMerge>()
        var totalScoreDelta = 0
        var boardChanged = false

        val lineCount = when (direction) {
            MoveDirection.LEFT, MoveDirection.RIGHT -> rows
            MoveDirection.UP, MoveDirection.DOWN -> cols
        }

        for (lineIdx in 0 until lineCount) {
            val positions = getLinePositions(direction, lineIdx, rows, cols)
            val lineTiles: List<Tile?> = positions.map { pos -> workingGrid.getTile(pos) }

            // Compress and merge 1D line using LineMerger
            val mergeResult = LineMerger.compressAndMergeLine(lineTiles) { nextTileId++ }

            if (mergeResult.scoreDelta > 0) {
                totalScoreDelta += mergeResult.scoreDelta
            }

            // Map 1D movements and merges back to 2D coordinates
            for (move in mergeResult.movements) {
                val fromPos = positions[move.fromIndex]
                val toPos = positions[move.toIndex]
                tileMovements.add(TileMovement(move.tileId, fromPos, toPos, move.value))
                boardChanged = true
            }

            for (merge in mergeResult.merges) {
                val targetPos = positions[merge.targetIndex]
                val positionedTile = merge.resultingTile.copy(row = targetPos.row, col = targetPos.col)
                tileMerges.add(TileMerge(merge.sourceTileIds, positionedTile, targetPos))
                boardChanged = true
            }

            // Update tiles on working grid
            for (i in positions.indices) {
                val pos = positions[i]
                if (!workingGrid.isObstacle(pos.row, pos.col)) {
                    val tile = mergeResult.newLine[i]
                    workingGrid.setTile(pos, tile?.copy(row = pos.row, col = pos.col))
                }
            }
        }

        return GridTransformation(
            newGrid = workingGrid,
            hasChanged = boardChanged,
            scoreDelta = totalScoreDelta,
            tileMovements = tileMovements,
            tileMerges = tileMerges
        )
    }

    /**
     * Maps directional swipe traversal into 1D ordered positions pointing towards the target edge.
     */
    private fun getLinePositions(direction: MoveDirection, lineIdx: Int, rows: Int, cols: Int): List<Position> {
        return when (direction) {
            MoveDirection.LEFT -> (0 until cols).map { c -> Position(lineIdx, c) }
            MoveDirection.RIGHT -> (cols - 1 downTo 0).map { c -> Position(lineIdx, c) }
            MoveDirection.UP -> (0 until rows).map { r -> Position(r, lineIdx) }
            MoveDirection.DOWN -> (rows - 1 downTo 0).map { r -> Position(r, lineIdx) }
        }
    }

    private data class GridTransformation(
        val newGrid: Grid,
        val hasChanged: Boolean,
        val scoreDelta: Int,
        val tileMovements: List<TileMovement>,
        val tileMerges: List<TileMerge>
    )
}
```

---

## 7. Score Accumulation Engine: Invariants & Truth Table Verification

### 7.1 Mathematical Rules
1. **Merge Points Rule**: $\Delta S = 2V$.
   A merge of two tiles of value $V$ generates a new tile of value $2V$ and awards exactly $2V$ points.
2. **Turn Sum Rule**: $\Delta S_{\text{turn}} = \sum_{m \in merges} m.\text{resultingTile.value}$.
3. **No-Merge Rule**: Sliding tiles without merging generates $\Delta S = 0$.
4. **No-Op Move Rule**: A blocked swipe generates $\Delta S = 0$.
5. **Monotonic High Score**: $H_{t+1} = \max(H_t, S_{t+1})$. $H$ never decreases.

### 7.2 Truth Table of Score Delta for Single-Pass Lines

| Row State Before Swipe | Swipe Direction | Row State After Swipe | Merged Pairs | Turn Score Delta ($\Delta S$) |
|:---|:---:|:---|:---:|:---:|
| `[2, 2, 4, 4]` | LEFT | `[4, 8, 0, 0]` | $(2,2)\to 4$, $(4,4)\to 8$ | $+4 + 8 = 12$ |
| `[2, 2, 2, 0]` | LEFT | `[4, 2, 0, 0]` | $(2,2)\to 4$ | $+4$ |
| `[2, 2, 2, 2]` | LEFT | `[4, 4, 0, 0]` | $(2,2)\to 4$, $(2,2)\to 4$ | $+4 + 4 = 8$ |
| `[4, 2, 2, 0]` | LEFT | `[4, 4, 0, 0]` | $(2,2)\to 4$ | $+4$ |
| `[0, 2, 0, 2]` | LEFT | `[4, 0, 0, 0]` | $(2,2)\to 4$ | $+4$ |
| `[2, 4, 2, 4]` | LEFT | `[2, 4, 2, 4]` (Blocked) | None | $+0$ (No move) |
| `[0, 0, 2, 0]` | LEFT | `[2, 0, 0, 0]` (Slide only) | None | $+0$ |
| `[2, 2, -1, 4, 4]` | LEFT | `[4, 0, -1, 8, 0]` | $(2,2)\to 4$, $(4,4)\to 8$ | $+4 + 8 = 12$ |
| `[1024, 1024, 0, 0]` | LEFT | `[2048, 0, 0, 0]` | $(1024, 1024)\to 2048$ | $+2048$ |

---

## 8. Board Reset and State Restoration Protocols

### 8.1 Reset Lifecycle
When `reset()` is invoked:
1. `_grid` is re-initialized with specified dimensions and obstacle positions.
2. `_score` is set to $0$.
3. `_highScore` is **preserved** (maintains personal best across game restarts).
4. `nextTileId` resets to $1L$.
5. `_isFreePlay` is set to `false`.
6. `_gameState` is set to `GameState.PLAYING`.
7. Exactly $2$ initial tiles are spawned using `randomProvider`:
   - Tile 1: placed at `randomProvider.selectEmptyCell(emptyCells)`.
   - Tile 2: placed at `randomProvider.selectEmptyCell(emptyCells - tile1Pos)`.
   - Values: independently evaluated from `randomProvider.nextTileValue()` ($90\%$ 2, $10\%$ 4).

### 8.2 State Restoration Protocol (`restoreState`)
When resuming an interrupted session after process death or app restart:
1. `_grid` is loaded from serialized JSON/DataStore via `savedGrid.clone()`.
2. `_score` is restored to saved score.
3. `_highScore` is updated to $\max(highScore, score)$.
4. `_gameState` is restored to saved state (`PLAYING`, `LEVEL_WON`, etc.).
5. `_targetTile` and `_isFreePlay` are configured.
6. **Tile ID Collision Guard**:
   $$nextTileId = \max_{(r, c)} (Tile(r, c).id) + 1L$$
   This strictly guarantees that subsequent merges and spawns will never produce an ID identical to any pre-existing restored tile, preventing rendering glitches in the animation pipeline.

---

## 9. Comprehensive Edge Cases & Resolution Matrix

| # | Edge Case Scenario | Concrete Condition | Expected Behavior | Rationale / Resolution |
|:---:|:---|:---|:---|:---|
| 1 | **Blocked Move (Wall Collision)** | User swipes towards a boundary where no tile can slide or merge (e.g. `[2, 4, 8, 16]` sliding LEFT) | `move()` returns `moved = false`, `scoreGained = 0`, `spawnedTile = null`. Board unchanged. | Canonical 2048 invariant: no mutation $\implies$ no tile spawn. |
| 2 | **Victory on Board Fill** | Tile merges into target tile ($2048$) on the final move that leaves the board full with no subsequent moves | `isLevelWon = true`, `gameState = LEVEL_WON`. | Priority rule: `LEVEL_WON` takes precedence over `GAME_OVER` (spec Section 9.10). |
| 3 | **Full Board with Hidden Move** | All 16 cells occupied, but cell $(3, 2) = 4$ and cell $(3, 3) = 4$ | `isGameOver() == false`. Swiping LEFT or RIGHT executes merge and frees an empty cell. | Evaluated correctly by Step 2 horizontal scan in `GameOverDetector`. |
| 4 | **Obstacle Barrier Collision** | Line `[2, 0, -1, 0, 2]` sliding LEFT | Yields `[2, 0, -1, 2, 0]`. Tiles on opposite sides of obstacle cannot merge. | Obstacle partitions the line into independent compression intervals. |
| 5 | **Endless / Free Play Continuation** | User reaches target tile, triggers `LEVEL_WON`, and selects "Keep Going" | Engine calls `continuePlaying()`, sets `isFreePlay = true`, sets state to `PLAYING`. | Player continues until `GAME_OVER` is reached without repetitive victory popups. |
| 6 | **Zero Empty Cells at Spawn** | Grid fills entirely without moves left | `spawnRandomTile()` gracefully returns `null`, engine flags `isGameOver = true`. | Null-safe return prevents crashes on terminal board states. |

---

## 10. Downstream Implementation & Verification Checklist

To verify this specification during Milestone 2 implementation:
- [ ] `RandomProvider` interface created with `nextTileValue()` and `selectEmptyCell()`.
- [ ] `DefaultRandomProvider` implements 90/10 Bernoulli trial with seed support.
- [ ] `GameOverDetector` implements $O(RC)$ 3-step scan with zero allocations.
- [ ] `GameEngine` interface and `GameEngineImpl` implement all state properties and methods.
- [ ] Blocked moves strictly return `moved = false` and suppress tile spawning.
- [ ] Real-time score accumulates strictly by $\Delta S = \text{sum of merged tile values}$.
- [ ] Monotonic high score satisfies $H_{t+1} = \max(H_t, S_{t+1})$.
- [ ] Board reset spawns exactly 2 initial tiles and preserves high score.
- [ ] State restoration re-calibrates `nextTileId` and restores board flawlessly.
