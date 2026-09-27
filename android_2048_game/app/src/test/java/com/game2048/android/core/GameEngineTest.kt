package com.game2048.android.core

import com.game2048.android.core.engine.GameEngine
import com.game2048.android.core.engine.GameEngineImpl
import com.game2048.android.core.model.GameSaveState
import com.game2048.android.core.model.GameState
import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.MoveDirection
import com.game2048.android.core.model.Position
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * Pure JVM unit tests for GameEngine swipe mechanics across 4 directions,
 * exact score accumulation, blocked move handling, game-over evaluation,
 * state restoration, and deterministic replayability.
 */
class GameEngineTest {

    private lateinit var randomProvider: SeededRandomProvider
    private lateinit var engine: GameEngine

    @Before
    fun setUp() {
        randomProvider = SeededRandomProvider(seed = 42L)
        engine = GameEngineImpl(randomProvider)
    }

    // --- Cardinal Direction Swipes ---

    @Test
    fun testSwipeLeft_compressesAndMergesTowardsColZero() {
        val initialGrid = gridOf(
            listOf(2, 2, 4, 4),
            listOf(0, 2, 0, 2),
            listOf(2, 4, 2, 4),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.LEFT)

        assertTrue(result.moved)
        assertEquals(16, result.scoreGained) // (2+2->4) + (4+4->8) + (2+2->4) = 16
        assertEquals(4, engine.grid.getValue(0, 0))
        assertEquals(8, engine.grid.getValue(0, 1))
        assertEquals(4, engine.grid.getValue(1, 0))
        assertEquals(2, engine.grid.getValue(2, 0))
        assertEquals(4, engine.grid.getValue(2, 1))
        assertEquals(2, engine.grid.getValue(2, 2))
        assertEquals(4, engine.grid.getValue(2, 3))
    }

    @Test
    fun testSwipeRight_compressesAndMergesTowardsMaxCol() {
        val initialGrid = gridOf(
            listOf(4, 4, 2, 2),
            listOf(2, 0, 2, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.RIGHT)

        assertTrue(result.moved)
        assertEquals(16, result.scoreGained) // (4+4->8) + (2+2->4) + (2+2->4) = 16
        assertEquals(8, engine.grid.getValue(0, 2))
        assertEquals(4, engine.grid.getValue(0, 3))
        assertEquals(4, engine.grid.getValue(1, 3))
    }

    @Test
    fun testSwipeUp_compressesAndMergesTowardsRowZero() {
        val initialGrid = gridOf(
            listOf(2, 0, 2, 0),
            listOf(2, 2, 4, 0),
            listOf(4, 0, 2, 0),
            listOf(4, 2, 4, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.UP)

        assertTrue(result.moved)
        // Col 0: [2, 2, 4, 4] -> [4, 8, 0, 0], score +12
        // Col 1: [0, 2, 0, 2] -> [4, 0, 0, 0], score +4
        // Col 2: [2, 4, 2, 4] -> [2, 4, 2, 4], score +0
        assertEquals(16, result.scoreGained)
        assertEquals(4, engine.grid.getValue(0, 0))
        assertEquals(8, engine.grid.getValue(1, 0))
        assertEquals(4, engine.grid.getValue(0, 1))
        assertEquals(2, engine.grid.getValue(0, 2))
        assertEquals(4, engine.grid.getValue(1, 2))
        assertEquals(2, engine.grid.getValue(2, 2))
        assertEquals(4, engine.grid.getValue(3, 2))
    }

    @Test
    fun testSwipeDown_compressesAndMergesTowardsMaxRow() {
        val initialGrid = gridOf(
            listOf(4, 2, 0, 0),
            listOf(4, 0, 0, 0),
            listOf(2, 2, 0, 0),
            listOf(2, 0, 0, 0)
        )
        engine.setGridState(initialGrid, score = 0)

        val result = engine.move(MoveDirection.DOWN)

        assertTrue(result.moved)
        // Col 0: [4, 4, 2, 2] downwards -> [8, 4] at bottom rows (2,3), score +12
        // Col 1: [2, 0, 2, 0] downwards -> [4] at bottom row 3, score +4
        assertEquals(16, result.scoreGained)
        assertEquals(8, engine.grid.getValue(2, 0))
        assertEquals(4, engine.grid.getValue(3, 0))
        assertEquals(4, engine.grid.getValue(3, 1))
    }

    // --- Scoring Verification ---

    @Test
    fun testExactScoreAccumulationOnSingleMerge() {
        val grid = gridOf(
            listOf(2, 2, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 100)

        val result = engine.move(MoveDirection.LEFT)

        assertEquals(4, result.scoreGained)
        assertEquals(104, engine.score)
    }

    @Test
    fun testScoreDoesNotIncrementOnPureSlideWithoutMerge() {
        val grid = gridOf(
            listOf(0, 0, 2, 0),
            listOf(0, 4, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 250)

        val result = engine.move(MoveDirection.LEFT)

        assertTrue(result.moved)
        assertEquals(0, result.scoreGained)
        assertEquals(250, engine.score)
    }

    @Test
    fun testHighScoreUpdatesMonotonically() {
        val grid = gridOf(
            listOf(2, 2, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 50)
        assertEquals(50, engine.highScore)

        engine.move(MoveDirection.LEFT) // +4 points -> score 54
        assertEquals(54, engine.score)
        assertEquals(54, engine.highScore)

        // Reset game; score becomes 0, but highScore remains 54
        engine.reset()
        assertEquals(0, engine.score)
        assertEquals(54, engine.highScore)
    }

    // --- Blocked Move / Spawn Suppression ---

    @Test
    fun testBlockedMoveDoesNotSpawnTileAndMaintainsState() {
        val grid = gridOf(
            listOf(4, 8, 16, 32),
            listOf(2, 4, 8, 16),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 500)
        val snapshotBefore = engine.grid.clone()

        // Swipe LEFT is already fully compressed against left boundary
        val result = engine.move(MoveDirection.LEFT)

        assertFalse("Move must be reported as not moved", result.moved)
        assertEquals(0, result.scoreGained)
        assertNull("No new tile should be spawned on a blocked move", result.spawnedTile)
        assertEquals(500, engine.score)
        assertEquals("Grid state must remain identical after blocked move", snapshotBefore, engine.grid)
    }

    // --- Game Over Evaluation ---

    @Test
    fun testGameOverTriggeredWhenGridIsFullWithNoAdjacentMatches() {
        // Checkerboard / alternating values with no horizontal or vertical matches
        val fullBlockedGrid = gridOf(
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2),
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2)
        )
        engine.setGridState(fullBlockedGrid, score = 1000)

        assertTrue("Game over should be detected when full with no matches", engine.isGameOver())
        assertEquals(GameState.GAME_OVER, engine.gameState)

        // All moves must fail
        assertFalse(engine.move(MoveDirection.UP).moved)
        assertFalse(engine.move(MoveDirection.DOWN).moved)
        assertFalse(engine.move(MoveDirection.LEFT).moved)
        assertFalse(engine.move(MoveDirection.RIGHT).moved)
    }

    @Test
    fun testGameOverNotTriggeredWhenFullGridHasHorizontalMerge() {
        val gridWithHorizontalMerge = gridOf(
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2),
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 4) // (3,2) and (3,3) can merge
        )
        engine.setGridState(gridWithHorizontalMerge, score = 1000)

        assertFalse("Game over should NOT trigger when horizontal merge exists", engine.isGameOver())
        assertEquals(GameState.PLAYING, engine.gameState)

        val result = engine.move(MoveDirection.RIGHT)
        assertTrue(result.moved)
        assertEquals(8, result.scoreGained)
        assertNotNull(result.spawnedTile)
    }

    @Test
    fun testGameOverNotTriggeredWhenFullGridHasVerticalMerge() {
        val gridWithVerticalMerge = gridOf(
            listOf(2, 4, 2, 4),
            listOf(4, 8, 4, 2),
            listOf(2, 8, 2, 4), // (1,1) and (2,1) both 8
            listOf(4, 2, 4, 2)
        )
        engine.setGridState(gridWithVerticalMerge, score = 1000)

        assertFalse("Game over should NOT trigger when vertical merge exists", engine.isGameOver())
        assertEquals(GameState.PLAYING, engine.gameState)

        val result = engine.move(MoveDirection.UP)
        assertTrue(result.moved)
        assertEquals(16, result.scoreGained)
    }

    @Test
    fun testGameOverWithObstaclesSeparatingMatchingTiles() {
        // Obstacle at (0, 1) prevents (0, 0) and (0, 2) from merging
        val obstacles = setOf(Position(0, 1))
        val grid = gridOf(
            listOf(2, -1, 2, 4),
            listOf(4, 2, 4, 2),
            listOf(2, 4, 2, 4),
            listOf(4, 2, 4, 2),
            obstacles = obstacles
        )
        engine.setGridState(grid, score = 500)

        assertTrue("Obstacle prevents horizontal merge, so game over should trigger", engine.isGameOver())
        assertEquals(GameState.GAME_OVER, engine.gameState)
    }

    // --- Deterministic Replayability ---

    @Test
    fun testDeterministicReplayabilityWithIdenticalSeeds() {
        val seed = 123456789L
        val moveSequence = listOf(
            MoveDirection.UP, MoveDirection.RIGHT, MoveDirection.DOWN, MoveDirection.LEFT,
            MoveDirection.UP, MoveDirection.RIGHT, MoveDirection.UP, MoveDirection.LEFT,
            MoveDirection.DOWN, MoveDirection.RIGHT, MoveDirection.UP, MoveDirection.LEFT
        )

        // Run 1
        val engine1 = GameEngineImpl(SeededRandomProvider(seed))
        engine1.startNewGame(rows = 4, cols = 4)
        val snapshots1 = ArrayList<Grid>()
        val scores1 = ArrayList<Int>()

        for (dir in moveSequence) {
            engine1.move(dir)
            snapshots1.add(engine1.grid.clone())
            scores1.add(engine1.score)
        }

        // Run 2
        val engine2 = GameEngineImpl(SeededRandomProvider(seed))
        engine2.startNewGame(rows = 4, cols = 4)
        val snapshots2 = ArrayList<Grid>()
        val scores2 = ArrayList<Int>()

        for (dir in moveSequence) {
            engine2.move(dir)
            snapshots2.add(engine2.grid.clone())
            scores2.add(engine2.score)
        }

        // Assert 100% bit-exact equivalence at every single turn
        for (i in moveSequence.indices) {
            assertEquals("Grid state diverged at step $i", snapshots1[i], snapshots2[i])
            assertEquals("Score diverged at step $i", scores1[i], scores2[i])
        }
    }

    @Test
    fun testReplayDivergesWithDifferentSeeds() {
        val moveSequence = listOf(
            MoveDirection.UP, MoveDirection.RIGHT, MoveDirection.DOWN, MoveDirection.LEFT,
            MoveDirection.UP, MoveDirection.RIGHT
        )

        val engine1 = GameEngineImpl(SeededRandomProvider(seed = 111L))
        engine1.startNewGame(4, 4)
        val engine2 = GameEngineImpl(SeededRandomProvider(seed = 999L))
        engine2.startNewGame(4, 4)

        for (dir in moveSequence) {
            engine1.move(dir)
            engine2.move(dir)
        }

        // Different seeds must generate different spawn placements
        assertNotEquals(engine1.grid, engine2.grid)
    }

    // --- Level Objective Victory Trigger ---

    @Test
    fun testLevelWonTriggeredWhenTargetTileReached() {
        val grid = gridOf(
            listOf(128, 128, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.startNewGame(targetTile = 256)
        engine.setGridState(grid, score = 0)

        val result = engine.move(MoveDirection.LEFT)

        assertTrue(result.moved)
        assertEquals(256, engine.grid.getValue(0, 0))
        assertTrue("Level won flag should be true when target 256 is merged", result.isLevelWon)
        assertTrue(engine.isLevelWon())
        assertEquals(GameState.LEVEL_WON, engine.gameState)

        // Continue playing in free play mode
        engine.continuePlaying()
        assertEquals(GameState.PLAYING, engine.gameState)
        assertTrue(engine.isFreePlay)
    }

    // --- Can Move Check ---

    @Test
    fun testCanMoveReportsAccuratelyWithoutMutatingState() {
        val grid = gridOf(
            listOf(2, 4, 8, 16),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0),
            listOf(0, 0, 0, 0)
        )
        engine.setGridState(grid, score = 100)
        val initialSnapshot = engine.grid.clone()

        // Can't move LEFT or UP (already at top-left)
        assertFalse(engine.canMove(MoveDirection.LEFT))
        assertFalse(engine.canMove(MoveDirection.UP))

        // Can move DOWN (slides into empty rows)
        assertTrue(engine.canMove(MoveDirection.DOWN))

        // State remains unmutated
        assertEquals(initialSnapshot, engine.grid)
        assertEquals(100, engine.score)
    }

    // --- State Restoration Protocol ---

    @Test
    fun testRestoreStateFromGameSaveState() {
        val saveState = GameSaveState(
            rows = 4,
            cols = 4,
            cells = listOf(
                listOf(2, 4, 8, 16),
                listOf(32, 64, 128, 256),
                listOf(512, 1024, 0, 0),
                listOf(0, 0, 0, -1)
            ),
            score = 12340,
            highScore = 20000,
            state = GameState.PLAYING,
            targetValue = 2048,
            levelId = 1
        )

        engine.restoreState(saveState)

        assertEquals(4, engine.grid.rows)
        assertEquals(4, engine.grid.cols)
        assertEquals(12340, engine.score)
        assertEquals(20000, engine.highScore)
        assertEquals(GameState.PLAYING, engine.gameState)
        assertEquals(2048, engine.targetTile)
        assertEquals(2, engine.grid.getValue(0, 0))
        assertEquals(1024, engine.grid.getValue(2, 1))
        assertEquals(-1, engine.grid.getValue(3, 3))
        assertTrue(engine.grid.isObstacle(3, 3))
    }
}
