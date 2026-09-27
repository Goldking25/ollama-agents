package com.game2048.android.core.engine

import com.game2048.android.core.model.Position
import kotlin.random.Random

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
