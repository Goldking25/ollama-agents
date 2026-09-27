package com.game2048.android.core.model

/**
 * High-level game state lifecycle.
 */
enum class GameState {
    IDLE,
    PLAYING,
    LEVEL_WON,
    GAME_OVER,
    PAUSED
}
