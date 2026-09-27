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
                if (!grid.isObstacle(r, c) && (grid.get(r, c) == null || grid.getValue(r, c) == 0)) {
                    return false
                }
            }
        }

        // Step 2: Check for adjacent horizontal mergeable pairs (col and col + 1)
        for (r in 0 until rows) {
            for (c in 0 until cols - 1) {
                if (grid.isObstacle(r, c) || grid.isObstacle(r, c + 1)) continue
                val valA = grid.getValue(r, c)
                val valB = grid.getValue(r, c + 1)
                if (valA > 0 && valA == valB) {
                    return false
                }
            }
        }

        // Step 3: Check for adjacent vertical mergeable pairs (row and row + 1)
        for (c in 0 until cols) {
            for (r in 0 until rows - 1) {
                if (grid.isObstacle(r, c) || grid.isObstacle(r + 1, c)) continue
                val valA = grid.getValue(r, c)
                val valB = grid.getValue(r + 1, c)
                if (valA > 0 && valA == valB) {
                    return false
                }
            }
        }

        return true
    }
}
