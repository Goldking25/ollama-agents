package com.game2048.android.core.model

/**
 * Records individual tile translation during a single turn.
 *
 * @property from Origin coordinate before move
 * @property to Target coordinate after move
 * @property tileId Unique identity of the moving tile
 * @property value Numerical face value of the moving tile
 */
data class TileMovement(
    val from: Position,
    val to: Position,
    val tileId: Long,
    val value: Int
)
