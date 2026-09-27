package com.game2048.android.core.engine

import com.game2048.android.core.model.GameSaveState
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
     */
    fun move(direction: MoveDirection): MoveResult

    /**
     * Checks if a move in the given direction would change board state, without mutating active state.
     */
    fun canMove(direction: MoveDirection): Boolean

    /**
     * Resets the board for the current dimensions and obstacles.
     */
    fun reset()

    /**
     * Resets the board with specified parameters.
     */
    fun reset(
        rows: Int = grid.rows,
        cols: Int = grid.cols,
        obstacles: List<Position> = emptyList(),
        targetTile: Int = 2048
    )

    /**
     * Configures and starts a new game with specified dimensions, target tile, and obstacles.
     */
    fun startNewGame(
        rows: Int = 4,
        cols: Int = 4,
        targetTile: Int = 2048,
        obstacles: Set<Position> = emptySet()
    )

    /**
     * Restores game state from an existing Grid and scores.
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
     * Restores game state from a [GameSaveState] snapshot.
     */
    fun restoreState(saveState: GameSaveState)

    /**
     * Enables endless/free play mode after achieving LEVEL_WON.
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

    /**
     * State injection helper for tests.
     */
    fun setGridState(grid: Grid, score: Int = 0)
}
