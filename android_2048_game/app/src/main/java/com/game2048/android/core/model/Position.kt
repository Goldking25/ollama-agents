package com.game2048.android.core.model

/**
 * Immutable 2D grid position coordinate.
 *
 * @property row 0-indexed row index [0 until rows]
 * @property col 0-indexed column index [0 until cols]
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
