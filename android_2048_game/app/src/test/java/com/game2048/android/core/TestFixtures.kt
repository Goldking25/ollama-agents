package com.game2048.android.core

import com.game2048.android.core.engine.RandomProvider
import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import kotlin.random.Random

/**
 * Deterministic PRNG implementation for test reproducibility.
 */
class SeededRandomProvider(val seed: Long) : RandomProvider {
    private val random = Random(seed)

    override fun nextTileValue(): Int {
        // Canonical 2048: 90% chance of 2, 10% chance of 4
        return if (random.nextFloat() < 0.90f) 2 else 4
    }

    override fun selectEmptyCell(emptyCells: List<Position>): Position {
        require(emptyCells.isNotEmpty()) { "Cannot select from empty cell list" }
        return emptyCells[random.nextInt(emptyCells.size)]
    }
}

/**
 * Scripted PRNG for step-by-step injection of exact spawn locations and values.
 */
class ScriptedRandomProvider(
    private val values: Iterator<Int>,
    private val cellSelectors: Iterator<(List<Position>) -> Position>
) : RandomProvider {

    constructor(
        fixedValues: List<Int>,
        fixedPositions: List<Position>
    ) : this(
        values = fixedValues.iterator(),
        cellSelectors = fixedPositions.map { target ->
            { cells: List<Position> ->
                cells.firstOrNull { it == target } ?: cells.first()
            }
        }.iterator()
    )

    override fun nextTileValue(): Int = if (values.hasNext()) values.next() else 2

    override fun selectEmptyCell(emptyCells: List<Position>): Position {
        return if (cellSelectors.hasNext()) cellSelectors.next().invoke(emptyCells) else emptyCells.first()
    }
}

/**
 * Helper to construct a Grid directly from a 2D integer array.
 */
fun gridOf(vararg rows: List<Int>, obstacles: Set<Position> = emptySet()): Grid {
    val rCount = rows.size
    val cCount = rows[0].size
    val allObstacles = obstacles.toMutableSet()
    for (r in 0 until rCount) {
        for (c in 0 until cCount) {
            if (rows[r][c] == -1) {
                allObstacles.add(Position(r, c))
            }
        }
    }
    val grid = Grid(rCount, cCount, allObstacles)
    var idCounter = 1L
    for (r in 0 until rCount) {
        for (c in 0 until cCount) {
            val v = rows[r][c]
            if (v > 0) {
                grid.set(r, c, Tile(id = idCounter++, value = v, row = r, col = c))
            }
        }
    }
    return grid
}
