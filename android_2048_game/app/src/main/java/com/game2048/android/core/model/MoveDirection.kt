package com.game2048.android.core.model

/**
 * Cardinal directions for swipe gestures and grid traversal.
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
