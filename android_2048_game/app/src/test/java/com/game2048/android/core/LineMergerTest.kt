package com.game2048.android.core

import com.game2048.android.core.engine.LineMerger
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Pure JVM unit tests for 1D line compression, single-pass non-double-merge invariant,
 * obstacle segmentation, and movement event tracking.
 */
class LineMergerTest {

    private var idCounter = 1L
    private fun nextId() = idCounter++

    private fun createTile(value: Int, col: Int = 0): Tile = Tile(id = nextId(), value = value, row = 0, col = col)

    private fun valuesToTiles(values: List<Int>): List<Tile?> {
        return values.mapIndexed { idx, v ->
            when (v) {
                0 -> null
                -1 -> Tile(id = -1L, value = -1, row = 0, col = idx)
                else -> createTile(v, idx)
            }
        }
    }

    private fun tilesToValues(tiles: List<Tile?>): List<Int> {
        return tiles.map { it?.value ?: 0 }
    }

    private fun assertLineMerge(
        input: List<Int>,
        expectedOutput: List<Int>,
        expectedScoreDelta: Int,
        expectedMoved: Boolean
    ) {
        val inputTiles = valuesToTiles(input)
        val result = LineMerger.compressAndMergeLine(inputTiles) { nextId() }

        assertEquals("Output values mismatch for input $input", expectedOutput, tilesToValues(result.newLine))
        assertEquals("Score delta mismatch for input $input", expectedScoreDelta, result.scoreGained)
        assertEquals("Moved flag mismatch for input $input", expectedMoved, result.moved)
    }

    // --- 16 Truth Table Edge Case Tests ---

    @Test
    fun testV01_dualIndependentMerges() {
        // [2, 2, 4, 4] -> [4, 8, 0, 0], score +12
        assertLineMerge(listOf(2, 2, 4, 4), listOf(4, 8, 0, 0), expectedScoreDelta = 12, expectedMoved = true)
    }

    @Test
    fun testV02_tripleIdenticalLeftPriority() {
        // [2, 2, 2, 0] -> [4, 2, 0, 0], score +4
        assertLineMerge(listOf(2, 2, 2, 0), listOf(4, 2, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV03_quadIdenticalNonCascade() {
        // [2, 2, 2, 2] -> [4, 4, 0, 0], score +8
        assertLineMerge(listOf(2, 2, 2, 2), listOf(4, 4, 0, 0), expectedScoreDelta = 8, expectedMoved = true)
    }

    @Test
    fun testV04_preExistingTargetValueNonMerge() {
        // [4, 2, 2, 0] -> [4, 4, 0, 0], score +4
        assertLineMerge(listOf(4, 2, 2, 0), listOf(4, 4, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV05_embeddedGapsCollapse() {
        // [0, 2, 0, 2] -> [4, 0, 0, 0], score +4
        assertLineMerge(listOf(0, 2, 0, 2), listOf(4, 0, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV06_obstaclePartitionMerge() {
        // [2, 2, -1, 4] -> [4, 0, -1, 4], score +4
        assertLineMerge(listOf(2, 2, -1, 4), listOf(4, 0, -1, 4), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV07_dualSegmentObstacleMerges() {
        // [2, 2, -1, 4, 4] -> [4, 0, -1, 8, 0], score +12
        assertLineMerge(listOf(2, 2, -1, 4, 4), listOf(4, 0, -1, 8, 0), expectedScoreDelta = 12, expectedMoved = true)
    }

    @Test
    fun testV08_obstacleImpassabilitySlide() {
        // [0, 2, -1, 0, 0] -> [2, 0, -1, 0, 0], score 0
        assertLineMerge(listOf(0, 2, -1, 0, 0), listOf(2, 0, -1, 0, 0), expectedScoreDelta = 0, expectedMoved = true)
    }

    @Test
    fun testV09_alternatingValuesBlocked() {
        // [2, 4, 2, 4] -> [2, 4, 2, 4], score 0, moved=false
        assertLineMerge(listOf(2, 4, 2, 4), listOf(2, 4, 2, 4), expectedScoreDelta = 0, expectedMoved = false)
    }

    @Test
    fun testV10_allEmptyCellsNoOp() {
        // [0, 0, 0, 0] -> [0, 0, 0, 0], score 0, moved=false
        assertLineMerge(listOf(0, 0, 0, 0), listOf(0, 0, 0, 0), expectedScoreDelta = 0, expectedMoved = false)
    }

    @Test
    fun testV11_isolatedSingleTileSlide() {
        // [0, 0, 2, 0] -> [2, 0, 0, 0], score 0, moved=true
        assertLineMerge(listOf(0, 0, 2, 0), listOf(2, 0, 0, 0), expectedScoreDelta = 0, expectedMoved = true)
    }

    @Test
    fun testV12_trailingPairMergeOnly() {
        // [8, 4, 2, 2] -> [8, 4, 4, 0], score +4
        assertLineMerge(listOf(8, 4, 2, 2), listOf(8, 4, 4, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV13_leadingPairCascadePrevention() {
        // [2, 2, 4, 8] -> [4, 4, 8, 0], score +4
        assertLineMerge(listOf(2, 2, 4, 8), listOf(4, 4, 8, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testV14_centerPairMerge() {
        // [2, 4, 4, 2] -> [2, 8, 2, 0], score +8
        assertLineMerge(listOf(2, 4, 4, 2), listOf(2, 8, 2, 0), expectedScoreDelta = 8, expectedMoved = true)
    }

    @Test
    fun testV15_farBoundaryLongSlide() {
        // [0, 0, 0, 2] -> [2, 0, 0, 0], score 0, moved=true
        assertLineMerge(listOf(0, 0, 0, 2), listOf(2, 0, 0, 0), expectedScoreDelta = 0, expectedMoved = true)
    }

    @Test
    fun testV16_doubleObstacleInteriorMerge() {
        // [-1, 2, 2, -1] -> [-1, 4, 0, -1], score +4
        assertLineMerge(listOf(-1, 2, 2, -1), listOf(-1, 4, 0, -1), expectedScoreDelta = 4, expectedMoved = true)
    }

    // --- Extended Multi-Dimension Lines ---

    @Test
    fun test3LengthLine_tightQuarters() {
        assertLineMerge(listOf(2, 2, 2), listOf(4, 2, 0), expectedScoreDelta = 4, expectedMoved = true)
        assertLineMerge(listOf(0, 4, 4), listOf(8, 0, 0), expectedScoreDelta = 8, expectedMoved = true)
        assertLineMerge(listOf(2, 4, 2), listOf(2, 4, 2), expectedScoreDelta = 0, expectedMoved = false)
    }

    @Test
    fun test5LengthLine_theMonolith() {
        assertLineMerge(listOf(2, 2, 2, 2, 2), listOf(4, 4, 2, 0, 0), expectedScoreDelta = 8, expectedMoved = true)
        assertLineMerge(listOf(4, 4, 8, 8, 16), listOf(8, 16, 16, 0, 0), expectedScoreDelta = 24, expectedMoved = true)
        assertLineMerge(listOf(0, 2, 0, 2, 0), listOf(4, 0, 0, 0, 0), expectedScoreDelta = 4, expectedMoved = true)
    }

    @Test
    fun testHighValueTileMerges() {
        assertLineMerge(listOf(1024, 1024, 2048, 2048), listOf(2048, 4096, 0, 0), expectedScoreDelta = 6144, expectedMoved = true)
        assertLineMerge(listOf(16384, 16384, 0, 0), listOf(32768, 0, 0, 0), expectedScoreDelta = 32768, expectedMoved = true)
    }

    // --- Animation Movement & Merge Event Tracking Tests ---

    @Test
    fun testTileMovementEventCoordinatesRecordedCorrectly() {
        val t1 = createTile(2, col = 3)
        val line = listOf(null, null, null, t1)
        val result = LineMerger.compressAndMergeLine(line)

        assertEquals(1, result.movements.size)
        val move = result.movements[0]
        assertEquals(t1.id, move.tileId)
        assertEquals(Position(0, 3), move.from)
        assertEquals(Position(0, 0), move.to)
    }

    @Test
    fun testTileMergeEventRecordsSourceIdsAndResultingTile() {
        val t1 = createTile(4, col = 1)
        val t2 = createTile(4, col = 3)
        val line = listOf(null, t1, null, t2)
        val result = LineMerger.compressAndMergeLine(line) { 999L }

        assertEquals(1, result.merges.size)
        val merge = result.merges[0]
        assertEquals(Pair(t1.id, t2.id), merge.sourceTileIds)
        assertEquals(999L, merge.resultingTile.id)
        assertEquals(8, merge.resultingTile.value)
        assertEquals(Position(0, 0), merge.targetPosition)
    }

    @Test
    fun testCompressAndMergeValuesHelper() {
        val (res, delta) = LineMerger.compressAndMergeValues(listOf(2, 0, 2, 4))
        assertEquals(listOf(4, 4, 0, 0), res)
        assertEquals(4, delta)
    }
}
