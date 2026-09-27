package com.game2048.android.core.engine

import com.game2048.android.core.model.GameSaveState
import com.game2048.android.core.model.GameState
import com.game2048.android.core.model.Grid
import com.game2048.android.core.model.MoveDirection
import com.game2048.android.core.model.MoveResult
import com.game2048.android.core.model.Position
import com.game2048.android.core.model.Tile
import com.game2048.android.core.model.TileMerge
import com.game2048.android.core.model.TileMovement

class GameEngineImpl(
    val randomProvider: RandomProvider = DefaultRandomProvider(),
    initialRows: Int = 4,
    initialCols: Int = 4,
    initialObstacles: List<Position> = emptyList(),
    initialTargetTile: Int = 2048,
    initialHighScore: Int = 0
) : GameEngine {

    constructor(
        initialRows: Int,
        initialCols: Int,
        initialObstacles: List<Position> = emptyList(),
        initialTargetTile: Int = 2048,
        initialHighScore: Int = 0,
        randomProvider: RandomProvider = DefaultRandomProvider()
    ) : this(randomProvider, initialRows, initialCols, initialObstacles, initialTargetTile, initialHighScore)

    private var _grid: Grid = Grid(initialRows, initialCols, initialObstacles.toSet())
    private var _score: Int = 0
    private var _highScore: Int = initialHighScore
    private var _gameState: GameState = GameState.IDLE
    private var _targetTile: Int = initialTargetTile
    private var _isFreePlay: Boolean = false

    private var nextTileId: Long = 1L

    override val grid: Grid get() = _grid
    override val score: Int get() = _score
    override val highScore: Int get() = _highScore
    override val gameState: GameState get() = _gameState
    override val targetTile: Int get() = _targetTile
    override val isFreePlay: Boolean get() = _isFreePlay

    init {
        reset(initialRows, initialCols, initialObstacles, initialTargetTile)
    }

    override fun move(direction: MoveDirection): MoveResult {
        if (_gameState == GameState.GAME_OVER || _gameState == GameState.IDLE) {
            return MoveResult(
                moved = false,
                scoreGained = 0,
                tileMovements = emptyList(),
                tileMerges = emptyList(),
                spawnedTile = null,
                isGameOver = (_gameState == GameState.GAME_OVER),
                isLevelWon = (_gameState == GameState.LEVEL_WON)
            )
        }

        val transformation = executeGridTransformation(direction, assignIds = true)

        if (!transformation.hasChanged) {
            return MoveResult(
                moved = false,
                scoreGained = 0,
                tileMovements = emptyList(),
                tileMerges = emptyList(),
                spawnedTile = null,
                isGameOver = isGameOver(),
                isLevelWon = isLevelWon()
            )
        }

        _grid = transformation.newGrid

        val scoreGained = transformation.scoreDelta
        _score += scoreGained
        if (_score > _highScore) {
            _highScore = _score
        }

        val spawnedTile = spawnRandomTile()

        var levelWonJustNow = false
        if (!_isFreePlay && _gameState != GameState.LEVEL_WON && checkLevelWon()) {
            _gameState = GameState.LEVEL_WON
            levelWonJustNow = true
        }

        val gameOver = GameOverDetector.isGameOver(_grid)
        if (gameOver && _gameState != GameState.LEVEL_WON) {
            _gameState = GameState.GAME_OVER
        }

        return MoveResult(
            moved = true,
            scoreGained = scoreGained,
            tileMovements = transformation.tileMovements,
            tileMerges = transformation.tileMerges,
            spawnedTile = spawnedTile,
            isGameOver = gameOver,
            isLevelWon = levelWonJustNow || (_gameState == GameState.LEVEL_WON)
        )
    }

    override fun canMove(direction: MoveDirection): Boolean {
        if (_gameState == GameState.GAME_OVER) return false
        val transformation = executeGridTransformation(direction, assignIds = false)
        return transformation.hasChanged
    }

    override fun reset() {
        reset(grid.rows, grid.cols, grid.obstacles.toList(), _targetTile)
    }

    override fun reset(
        rows: Int,
        cols: Int,
        obstacles: List<Position>,
        targetTile: Int
    ) {
        _grid = Grid(rows, cols, obstacles.toSet())
        _score = 0
        _targetTile = targetTile
        _isFreePlay = false
        _gameState = GameState.PLAYING
        nextTileId = 1L

        spawnRandomTile()
        spawnRandomTile()
    }

    override fun startNewGame(
        rows: Int,
        cols: Int,
        targetTile: Int,
        obstacles: Set<Position>
    ) {
        reset(rows, cols, obstacles.toList(), targetTile)
    }

    override fun restoreState(
        savedGrid: Grid,
        score: Int,
        highScore: Int,
        gameState: GameState,
        targetTile: Int,
        isFreePlay: Boolean
    ) {
        _grid = savedGrid.clone()
        _score = score
        _highScore = maxOf(highScore, score)
        _gameState = gameState
        _targetTile = targetTile
        _isFreePlay = isFreePlay

        val maxId = _grid.getAllTiles().maxOfOrNull { it.id } ?: 0L
        nextTileId = maxId + 1L
    }

    override fun restoreState(saveState: GameSaveState) {
        val obstacles = mutableSetOf<Position>()
        for (r in 0 until saveState.rows) {
            for (c in 0 until saveState.cols) {
                if (saveState.cells[r][c] == Tile.OBSTACLE_VALUE) {
                    obstacles.add(Position(r, c))
                }
            }
        }
        val restoredGrid = Grid(saveState.rows, saveState.cols, obstacles)
        var maxId = 0L
        for (r in 0 until saveState.rows) {
            for (c in 0 until saveState.cols) {
                val v = saveState.cells[r][c]
                if (v > 0) {
                    val tileId = ++maxId
                    restoredGrid.set(r, c, Tile(id = tileId, value = v, row = r, col = c))
                }
            }
        }
        restoreState(
            savedGrid = restoredGrid,
            score = saveState.score,
            highScore = saveState.highScore,
            gameState = saveState.state,
            targetTile = saveState.targetValue,
            isFreePlay = false
        )
    }

    override fun continuePlaying() {
        if (_gameState == GameState.LEVEL_WON) {
            _isFreePlay = true
            _gameState = GameState.PLAYING
        }
    }

    override fun isGameOver(): Boolean = GameOverDetector.isGameOver(_grid)

    override fun isLevelWon(): Boolean = checkLevelWon()

    override fun setGridState(grid: Grid, score: Int) {
        _grid = grid.clone()
        _score = score
        if (_score > _highScore) {
            _highScore = _score
        }
        val maxId = _grid.getAllTiles().maxOfOrNull { it.id } ?: 0L
        nextTileId = maxId + 1L

        if (checkLevelWon() && !_isFreePlay) {
            _gameState = GameState.LEVEL_WON
        } else if (GameOverDetector.isGameOver(_grid)) {
            _gameState = GameState.GAME_OVER
        } else {
            _gameState = GameState.PLAYING
        }
    }

    private fun checkLevelWon(): Boolean {
        for (r in 0 until _grid.rows) {
            for (c in 0 until _grid.cols) {
                val tile = _grid.get(r, c)
                if (tile != null && tile.value >= _targetTile) {
                    return true
                }
            }
        }
        return false
    }

    private fun spawnRandomTile(): Tile? {
        val emptyCells = _grid.emptyCells()
        if (emptyCells.isEmpty()) return null

        val selectedPos = randomProvider.selectEmptyCell(emptyCells)
        val value = randomProvider.nextTileValue()
        val tile = Tile(
            id = nextTileId++,
            value = value,
            isNew = true,
            row = selectedPos.row,
            col = selectedPos.col
        )
        _grid.set(selectedPos, tile)
        return tile
    }

    private fun executeGridTransformation(direction: MoveDirection, assignIds: Boolean): GridTransformation {
        val rows = _grid.rows
        val cols = _grid.cols
        val workingGrid = _grid.clone()

        val tileMovements = mutableListOf<TileMovement>()
        val tileMerges = mutableListOf<TileMerge>()
        var totalScoreDelta = 0
        var boardChanged = false

        val lineCount = when (direction) {
            MoveDirection.LEFT, MoveDirection.RIGHT -> rows
            MoveDirection.UP, MoveDirection.DOWN -> cols
        }

        val idGen: () -> Long = if (assignIds) {
            { nextTileId++ }
        } else {
            { -1L }
        }

        for (lineIdx in 0 until lineCount) {
            val positions = getLinePositions(direction, lineIdx, rows, cols)
            val lineTiles: List<Tile?> = positions.map { pos -> workingGrid.get(pos) }

            val mergeResult = LineMerger.compressAndMergeLine(lineTiles, positions, idGen)

            if (mergeResult.scoreGained > 0) {
                totalScoreDelta += mergeResult.scoreGained
            }

            tileMovements.addAll(mergeResult.movements)
            tileMerges.addAll(mergeResult.merges)

            if (mergeResult.moved) {
                boardChanged = true
            }

            for (i in positions.indices) {
                val pos = positions[i]
                if (!workingGrid.isObstacle(pos.row, pos.col)) {
                    workingGrid.set(pos, mergeResult.newLine[i])
                }
            }
        }

        return GridTransformation(
            newGrid = workingGrid,
            hasChanged = boardChanged,
            scoreDelta = totalScoreDelta,
            tileMovements = tileMovements,
            tileMerges = tileMerges
        )
    }

    private fun getLinePositions(direction: MoveDirection, lineIdx: Int, rows: Int, cols: Int): List<Position> {
        return when (direction) {
            MoveDirection.LEFT -> (0 until cols).map { c -> Position(lineIdx, c) }
            MoveDirection.RIGHT -> (cols - 1 downTo 0).map { c -> Position(lineIdx, c) }
            MoveDirection.UP -> (0 until rows).map { r -> Position(r, lineIdx) }
            MoveDirection.DOWN -> (rows - 1 downTo 0).map { r -> Position(r, lineIdx) }
        }
    }

    private data class GridTransformation(
        val newGrid: Grid,
        val hasChanged: Boolean,
        val scoreDelta: Int,
        val tileMovements: List<TileMovement>,
        val tileMerges: List<TileMerge>
    )
}
