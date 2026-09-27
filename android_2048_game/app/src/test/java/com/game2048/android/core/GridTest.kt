package com.game2048.android.core

import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
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
