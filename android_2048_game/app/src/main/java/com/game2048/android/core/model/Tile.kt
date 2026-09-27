package com.game2048.android.core.model

/**
 * Immutable representation of a tile on the game board.
 * Maintains persistent identity ([id]) across turns to enable smooth UI animation interpolation.
 *
 * @property id Globally unique persistent identifier (> 0 for active tiles, -1 for obstacles)
 * @property value Tile value (power of 2: 2, 4, 8, ..., 65536; or [OBSTACLE_VALUE] = -1)
 * @property isNew Flag indicating if this tile was just spawned in the current turn
 * @property mergedFrom Pair of tile IDs that merged to form this tile, or null if spawned
 * @property row Current grid row
 * @property col Current grid column
 */
data class Tile(
    val id: Long,
    val value: Int,
    val isNew: Boolean = false,
    val mergedFrom: Pair<Long, Long>? = null,
    val row: Int = 0,
    val col: Int = 0
) {
    constructor(id: Long, value: Int, row: Int, col: Int) : this(id, value, false, null, row, col)
    constructor(id: Long, value: Int, position: Position) : this(id, value, false, null, position.row, position.col)

    val position: Position get() = Position(row, col)
    val isObstacle: Boolean get() = value == OBSTACLE_VALUE
    val isEmpty: Boolean get() = value == 0
    val isPlayable: Boolean get() = value > 0

    companion object {
        const val OBSTACLE_VALUE: Int = -1
        const val OBSTACLE_ID: Long = -1L

        fun createObstacle(position: Position): Tile =
            Tile(id = OBSTACLE_ID, value = OBSTACLE_VALUE, row = position.row, col = position.col)

        fun createObstacle(row: Int, col: Int): Tile =
            Tile(id = OBSTACLE_ID, value = OBSTACLE_VALUE, row = row, col = col)
    }
}
