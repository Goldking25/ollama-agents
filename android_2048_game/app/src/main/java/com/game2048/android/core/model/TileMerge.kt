package com.game2048.android.core.model

/**
 * Records collision and fusion of two tiles into a new tile.
 *
 * @property sourceTileIds IDs of the two tiles merged
 * @property resultingTile The newly created tile
 * @property targetPosition The destination position where the merge occurred
 */
data class TileMerge(
    val sourceTileIds: Pair<Long, Long>,
    val resultingTile: Tile,
    val targetPosition: Position = resultingTile.position
) {
    constructor(sourceTileIds: Pair<Long, Long>, resultingTile: Tile) : this(sourceTileIds, resultingTile, resultingTile.position)
}
