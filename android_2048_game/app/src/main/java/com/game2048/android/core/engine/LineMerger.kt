package com.game2048.android.core.engine

import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import com.game2048.android.core.model.TileMerge
import com.game2048.android.core.model.TileMovement

typealias LineMergeResult = LineMerger.LineResult

object LineMerger {

    data class LineResult(
        val newLine: List<Tile?>,
        val movements: List<TileMovement>,
        val merges: List<TileMerge>,
        val scoreGained: Int,
        val moved: Boolean = movements.isNotEmpty() || merges.isNotEmpty()
    ) {
        val scoreDelta: Int get() = scoreGained
    }

    /**
     * Compresses and merges a 1D line towards index 0 using default linear positions.
     */
    fun compressAndMergeLine(
        line: List<Tile?>,
        idGenerator: () -> Long
    ): LineResult = compressAndMergeLine(line, line.indices.map { Position(0, it) }, idGenerator)

    /**
     * Compresses and merges a 1D line towards index 0.
     * Enforces the single-pass non-double-merge invariant and obstacle partitioning.
     *
     * @param line Tiles in the line (null for empty, value = -1 for obstacle)
     * @param positions 2D positions corresponding to each index in [line]
     * @param idGenerator Provider of globally unique IDs for newly created merged tiles
     */
    fun compressAndMergeLine(
        line: List<Tile?>,
        positions: List<Position> = line.indices.map { Position(0, it) },
        idGenerator: () -> Long = { System.nanoTime() }
    ): LineResult {
        require(line.size == positions.size) {
            "Line size (${line.size}) must match positions size (${positions.size})"
        }

        val n = line.size
        val resultLine = arrayOfNulls<Tile>(n)
        val movements = mutableListOf<TileMovement>()
        val merges = mutableListOf<TileMerge>()
        var totalScore = 0

        var segStart = 0
        for (i in 0 until n) {
            val tile = line[i]
            if (tile != null && tile.isObstacle) {
                // Process playable segment before obstacle
                if (segStart < i) {
                    val segResult = processSegment(line, positions, segStart, i - 1, idGenerator)
                    for (k in segStart until i) {
                        resultLine[k] = segResult.newLine[k]
                    }
                    movements.addAll(segResult.movements)
                    merges.addAll(segResult.merges)
                    totalScore += segResult.scoreGained
                }
                // Fix obstacle at current index
                resultLine[i] = tile
                segStart = i + 1
            }
        }

        // Process final segment after last obstacle
        if (segStart < n) {
            val segResult = processSegment(line, positions, segStart, n - 1, idGenerator)
            for (k in segStart until n) {
                resultLine[k] = segResult.newLine[k]
            }
            movements.addAll(segResult.movements)
            merges.addAll(segResult.merges)
            totalScore += segResult.scoreGained
        }

        return LineResult(
            newLine = resultLine.toList(),
            movements = movements,
            merges = merges,
            scoreGained = totalScore
        )
    }

    private data class IndexedTile(val tile: Tile, val lineIndex: Int)

    private fun processSegment(
        line: List<Tile?>,
        positions: List<Position>,
        start: Int,
        end: Int,
        idGenerator: () -> Long
    ): LineResult {
        val nonEmpties = mutableListOf<IndexedTile>()
        for (idx in start..end) {
            val t = line[idx]
            if (t != null && !t.isObstacle && t.value > 0) {
                nonEmpties.add(IndexedTile(t, idx))
            }
        }

        val segResult = arrayOfNulls<Tile>(line.size)
        val movements = mutableListOf<TileMovement>()
        val merges = mutableListOf<TileMerge>()
        var scoreGained = 0

        var targetIdx = start
        var i = 0
        while (i < nonEmpties.size) {
            val current = nonEmpties[i]
            val next = if (i + 1 < nonEmpties.size) nonEmpties[i + 1] else null

            if (next != null && current.tile.value == next.tile.value) {
                val mergedValue = current.tile.value * 2
                val targetPos = positions[targetIdx]
                val resultingTile = Tile(
                    id = idGenerator(),
                    value = mergedValue,
                    isNew = false,
                    mergedFrom = Pair(current.tile.id, next.tile.id),
                    row = targetPos.row,
                    col = targetPos.col
                )

                if (current.lineIndex != targetIdx) {
                    movements.add(
                        TileMovement(
                            from = positions[current.lineIndex],
                            to = targetPos,
                            tileId = current.tile.id,
                            value = current.tile.value
                        )
                    )
                }
                movements.add(
                    TileMovement(
                        from = positions[next.lineIndex],
                        to = targetPos,
                        tileId = next.tile.id,
                        value = next.tile.value
                    )
                )

                merges.add(
                    TileMerge(
                        sourceTileIds = Pair(current.tile.id, next.tile.id),
                        resultingTile = resultingTile,
                        targetPosition = targetPos
                    )
                )

                segResult[targetIdx] = resultingTile
                scoreGained += mergedValue
                targetIdx++
                i += 2
            } else {
                val targetPos = positions[targetIdx]
                if (current.lineIndex != targetIdx) {
                    movements.add(
                        TileMovement(
                            from = positions[current.lineIndex],
                            to = targetPos,
                            tileId = current.tile.id,
                            value = current.tile.value
                        )
                    )
                }
                val movedTile = if (current.tile.row != targetPos.row || current.tile.col != targetPos.col) {
                    current.tile.copy(row = targetPos.row, col = targetPos.col)
                } else {
                    current.tile
                }
                segResult[targetIdx] = movedTile
                targetIdx++
                i += 1
            }
        }

        return LineResult(
            newLine = segResult.toList(),
            movements = movements,
            merges = merges,
            scoreGained = scoreGained
        )
    }

    /**
     * Mathematical helper transforming an integer array towards index 0.
     * Values: 0 for empty, -1 for obstacle, > 0 for tile.
     * Returns Pair(resultingArray, scoreDelta).
     */
    fun compressAndMergeValues(values: List<Int>): Pair<List<Int>, Int> {
        var idCounter = 1L
        val tiles = values.mapIndexed { idx, v ->
            when (v) {
                0 -> null
                Tile.OBSTACLE_VALUE -> Tile.createObstacle(0, idx)
                else -> Tile(id = idCounter++, value = v, row = 0, col = idx)
            }
        }
        val result = compressAndMergeLine(tiles) { idCounter++ }
        val outValues = result.newLine.map { it?.value ?: 0 }
        return Pair(outValues, result.scoreGained)
    }
}
