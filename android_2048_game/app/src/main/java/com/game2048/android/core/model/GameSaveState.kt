package com.game2048.android.core.model

/**
 * Serializable snapshot of the active game session.
 *
 * @property rows Board row dimension
 * @property cols Board column dimension
 * @property cells 2D matrix of integer tile values (0 = empty, -1 = obstacle, > 0 = tile value)
 * @property score Current accumulated score
 * @property highScore Historical personal best score
 * @property state Active game lifecycle state
 * @property targetValue Target tile value required to clear this level (e.g. 2048)
 * @property levelId Level ID associated with this session (1-based index or special level)
 */
data class GameSaveState(
    val rows: Int,
    val cols: Int,
    val cells: List<List<Int>>,
    val score: Int,
    val highScore: Int,
    val state: GameState,
    val targetValue: Int,
    val levelId: Int
)
