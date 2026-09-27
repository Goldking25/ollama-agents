package com.game2048.android.core.model

/**
 * Comprehensive turn result payload returned by [GameEngine.move].
 * Supplies the presentation layer with all animation events and state deltas.
 *
 * @property moved True if at least one tile slid or merged; false on blocked/no-op moves
 * @property scoreGained Numerical score gained from merges formed during this move (sum of 2V)
 * @property tileMovements List of tile translation events during the slide phase
 * @property tileMerges List of tile collision/fusion events
 * @property spawnedTile Newly spawned tile (strictly null if moved is false)
 * @property isGameOver True if no further moves are possible in any direction
 * @property isLevelWon True if a tile with target value was achieved in this turn
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
