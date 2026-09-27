package com.game2048.android.core.model

/**
 * Arbitrary-dimension 2D grid representation supporting standard sizes (3x3, 4x4, 5x5)
 * and impassable obstacle cells (-1).
 *
 * @property rows Number of rows (must be between 2 and 8 inclusive)
 * @property cols Number of columns (must be between 2 and 8 inclusive)
 * @property initialObstacles Optional set of coordinates configured as fixed obstacle cells (-1)
 */
class Grid(
    val rows: Int,
    val cols: Int,
    initialObstacles: Set<Position> = emptySet()
) {
    init {
        require(rows in MIN_DIMENSION..MAX_DIMENSION) {
            "Row count must be between $MIN_DIMENSION and $MAX_DIMENSION, was: $rows"
        }
        require(cols in MIN_DIMENSION..MAX_DIMENSION) {
            "Column count must be between $MIN_DIMENSION and $MAX_DIMENSION, was: $cols"
        }
        for (obs in initialObstacles) {
            require(isInBounds(obs)) {
                "Obstacle coordinate $obs is outside grid dimensions ($rows x $cols)"
            }
        }
    }

    constructor(rows: Int, cols: Int, obstacles: List<Position>) : this(rows, cols, obstacles.toSet())

    val obstacles: Set<Position> = initialObstacles.toSet()

    private val cells: Array<Array<Tile?>> = Array(rows) { r ->
        Array(cols) { c ->
            val pos = Position(r, c)
            if (pos in obstacles) Tile.createObstacle(r, c) else null
        }
    }

    fun isInBounds(row: Int, col: Int): Boolean = row in 0 until rows && col in 0 until cols
    fun isInBounds(pos: Position): Boolean = isInBounds(pos.row, pos.col)
    fun isWithinBounds(row: Int, col: Int): Boolean = isInBounds(row, col)
    fun isWithinBounds(pos: Position): Boolean = isInBounds(pos)

    operator fun get(row: Int, col: Int): Tile? {
        if (!isInBounds(row, col)) {
            throw IndexOutOfBoundsException("Position ($row, $col) out of bounds for ${rows}x${cols} grid")
        }
        return cells[row][col]
    }

    operator fun get(pos: Position): Tile? = get(pos.row, pos.col)
    fun getTile(row: Int, col: Int): Tile? = get(row, col)
    fun getTile(pos: Position): Tile? = get(pos.row, pos.col)

    fun getValue(row: Int, col: Int): Int {
        if (!isInBounds(row, col)) return 0
        return cells[row][col]?.value ?: 0
    }

    fun getValue(pos: Position): Int = getValue(pos.row, pos.col)

    operator fun set(row: Int, col: Int, tile: Tile?) {
        if (!isInBounds(row, col)) {
            throw IndexOutOfBoundsException("Position ($row, $col) out of bounds for ${rows}x${cols} grid")
        }
        val pos = Position(row, col)
        if (isObstacle(row, col)) {
            check(tile?.isObstacle == true) { "Cannot overwrite obstacle cell at $pos" }
        }
        cells[row][col] = tile?.copy(row = row, col = col)
    }

    operator fun set(pos: Position, tile: Tile?) = set(pos.row, pos.col, tile)
    fun setTile(row: Int, col: Int, tile: Tile?) = set(row, col, tile)
    fun setTile(pos: Position, tile: Tile?) = set(pos.row, pos.col, tile)
    fun setTile(tile: Tile?) {
        if (tile != null) {
            set(tile.row, tile.col, tile)
        }
    }

    fun isObstacle(row: Int, col: Int): Boolean = Position(row, col) in obstacles || (isInBounds(row, col) && cells[row][col]?.isObstacle == true)
    fun isObstacle(pos: Position): Boolean = isObstacle(pos.row, pos.col)

    fun isEmpty(row: Int, col: Int): Boolean = isInBounds(row, col) && !isObstacle(row, col) && (cells[row][col] == null || cells[row][col]?.isEmpty == true)
    fun isEmpty(pos: Position): Boolean = isEmpty(pos.row, pos.col)

    fun emptyCells(): List<Position> {
        val result = ArrayList<Position>()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val pos = Position(r, c)
                if (pos !in obstacles && cells[r][c] == null) {
                    result.add(pos)
                }
            }
        }
        return result
    }

    fun getEmptyCells(): List<Position> = emptyCells()
    fun getEmptyPositions(): List<Position> = emptyCells()

    fun getAllTiles(): List<Tile> {
        val result = ArrayList<Tile>()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val t = cells[r][c]
                if (t != null && !t.isObstacle && t.value > 0) {
                    result.add(t)
                }
            }
        }
        return result
    }

    fun clear() {
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val pos = Position(r, c)
                if (pos !in obstacles) {
                    cells[r][c] = null
                }
            }
        }
    }

    fun clone(): Grid {
        val copy = Grid(rows, cols, obstacles)
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                val t = cells[r][c]
                if (t != null && !t.isObstacle) {
                    copy.cells[r][c] = t.copy()
                }
            }
        }
        return copy
    }

    fun copy(): Grid = clone()

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is Grid) return false
        if (rows != other.rows || cols != other.cols) return false
        if (obstacles != other.obstacles) return false
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                if (getValue(r, c) != other.getValue(r, c)) return false
            }
        }
        return true
    }

    override fun hashCode(): Int {
        var result = rows.hashCode()
        result = 31 * result + cols.hashCode()
        result = 31 * result + obstacles.hashCode()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                result = 31 * result + getValue(r, c).hashCode()
            }
        }
        return result
    }

    override fun toString(): String = buildString {
        append("Grid(${rows}x${cols}):\n")
        for (r in 0 until rows) {
            append("[")
            for (c in 0 until cols) {
                val v = getValue(r, c)
                val s = when (v) {
                    0 -> "."
                    Tile.OBSTACLE_VALUE -> "X"
                    else -> v.toString()
                }
                append(s.padStart(5))
                if (c < cols - 1) append(", ")
            }
            append("]\n")
        }
    }

    companion object {
        const val MIN_DIMENSION: Int = 2
        const val MAX_DIMENSION: Int = 8
    }
}
