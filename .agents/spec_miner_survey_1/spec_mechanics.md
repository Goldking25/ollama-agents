# 2048 Game Mechanics & Progressive Level System Specification

**Document Version:** 1.0.0  
**Author:** survey_spec_mechanics (Specification Miner)  
**Status:** Approved for Implementation & Test Suite Formulation  
**Target Systems:** Android 12 (API 31) through Android 15 (API 35)  
**Workspace Path:** `android_2048_game`  

---

## 1. Executive Summary & Architecture Overview

This document specifies the exact behavioral, algorithmic, mathematical, and user-experience contracts for the 2048 Android application as mandated by `ORIGINAL_REQUEST.md`. It provides unambiguous specifications for:
1. **Core 2048 Engine**: Deterministic grid transformations, single-pass merge semantics, tile sliding rules, spawn mechanics, scoring, and termination predicates.
2. **Progressive Level System**: Multi-stage progression across varied board dimensions ($3 \times 3$, $4 \times 4$, $5 \times 5$), obstacle cells, escalating target thresholds, level unlock states, and persistence.
3. **Fluid 60+ FPS Animation & Touch UX**: Motion pipelines, easing curves, input buffering/queueing, and zero-allocation draw constraints.

All algorithms specified herein are deterministic and decoupled from the presentation layer to guarantee 100% testability via headless unit tests.

---

## 2. Core 2048 Mathematical & Logical Model

### 2.1 Grid Coordinate System & State Representation

The game board is represented as an $R \times C$ two-dimensional grid:
$$\mathcal{G} \in \mathbb{Z}^{R \times C}$$
where $R$ is the number of rows and $C$ is the number of columns. For the standard 2048 game, $R = 4, C = 4$.

Coordinates are defined as:
$$\text{Cell}(r, c), \quad r \in \{0, 1, \dots, R - 1\}, \quad c \in \{0, 1, \dots, C - 1\}$$
- $r = 0$: Topmost row.
- $r = R - 1$: Bottommost row.
- $c = 0$: Leftmost column.
- $c = C - 1$: Rightmost column.

Each cell $\mathcal{G}(r, c)$ contains an integer state value:
- $\mathcal{G}(r, c) = 0$: Empty cell.
- $\mathcal{G}(r, c) = 2^k \ (k \in \{1, 2, \dots, 16\})$: Active tile displaying value $2^k \in \{2, 4, 8, 16, \dots, 65536\}$.
- $\mathcal{G}(r, c) = -1$: Obstacle / impassable cell (applicable in advanced progressive levels).

### 2.2 Tile Data Model & Unique Identifiers

To decouple state progression from rendering and support continuous animation interpolation, each active tile maintains an immutable identity:
```kotlin
data class Tile(
    val id: Long,            // Globally unique auto-incrementing ID
    val value: Int,          // Value: 2, 4, 8, 16, ..., 2048, etc.
    val row: Int,            // Current row [0..R-1]
    val col: Int             // Current column [0..C-1]
)
```

During a single turn transition $t \to t+1$, tiles undergo transformations categorized as:
1. **Stationary**: Tile remains at $(r, c)$ with unchanged value.
2. **Moved**: Tile at $(r_1, c_1)$ translates to $(r_2, c_2)$ without merging.
3. **Merged**: Tile $A$ and Tile $B$ translate to $(r_m, c_m)$ and merge into a newly generated Tile $C$ with $C.\text{value} = A.\text{value} + B.\text{value}$.
4. **Spawned**: Newly created Tile $S$ appears at empty cell $(r_s, c_s)$.

### 2.3 Cardinal Direction Vectors & Coordinate Transforms

The 4 swipe directions $\mathcal{D} = \{\text{UP}, \text{DOWN}, \text{LEFT}, \text{RIGHT}\}$ are represented by unit displacement vectors $(\Delta r, \Delta c)$:
$$\vec{d}_{\text{UP}} = (-1, 0), \quad \vec{d}_{\text{DOWN}} = (+1, 0), \quad \vec{d}_{\text{LEFT}} = (0, -1), \quad \vec{d}_{\text{RIGHT}} = (0, +1)$$

To eliminate redundant code and prevent dimensional bugs, any 2D slide operation in direction $\mathcal{D}$ is normalized to a 1D slide operation along lines (rows or columns) pointing towards the boundary.

| Direction | Primary Iteration Line | Traversal Order towards Destination Edge |
|:---|:---|:---|
| **LEFT** | Rows $r \in [0, R-1]$ | Index $c$ from $0$ to $C-1$ |
| **RIGHT** | Rows $r \in [0, R-1]$ | Index $c$ from $C-1$ down to $0$ |
| **UP** | Columns $c \in [0, C-1]$ | Index $r$ from $0$ to $R-1$ |
| **DOWN** | Columns $c \in [0, C-1]$ | Index $r$ from $R-1$ down to $0$ |

### 2.4 The Deterministic 1D Slide-and-Merge Algorithm

Every line of length $L$ containing cells $[c_0, c_1, \dots, c_{L-1}]$ undergoes a single-pass compression towards index $0$.

#### Formal Algorithm: `compressAndMergeLine(line: List<Tile?>): LineResult`
```
Input: Array of size L, where each element is either a Tile or null (empty).
Output: 
  - newLine: Array of size L
  - movements: List of TileMove(tileId, fromIdx, toIdx)
  - merges: List of TileMerge(sourceTileId1, sourceTileId2, resultingTileId, mergedValue, targetIdx)
  - lineScoreDelta: Int

1. Filter non-empty tiles from line while preserving original indices:
   nonEmpty = [(tile, originalIdx) for idx, tile in enumerate(line) if tile != null and tile.value > 0]

2. Initialize:
   targetIdx = 0
   skipNext = false
   newLine = [null] * L
   movements = []
   merges = []
   lineScoreDelta = 0

3. Loop i from 0 to len(nonEmpty) - 1:
   if skipNext:
       skipNext = false
       continue

   currentTile, currentOrigIdx = nonEmpty[i]

   // Check if merge with next tile is possible
   if i + 1 < len(nonEmpty) and currentTile.value == nonEmpty[i + 1].tile.value:
       nextTile, nextOrigIdx = nonEmpty[i + 1]
       mergedValue = currentTile.value * 2
       newTile = Tile(newUniqueId(), mergedValue, targetIdx)
       
       newLine[targetIdx] = newTile
       merges.append(TileMerge(currentTile.id, nextTile.id, newTile.id, mergedValue, targetIdx))
       lineScoreDelta += mergedValue
       
       skipNext = true
       targetIdx += 1
   else:
       // Tile moves without merging
       if currentOrigIdx != targetIdx:
           movements.append(TileMove(currentTile.id, currentOrigIdx, targetIdx))
       newLine[targetIdx] = currentTile.copy(index = targetIdx)
       targetIdx += 1

4. Fill remaining indices [targetIdx .. L-1] with null.
5. Return (newLine, movements, merges, lineScoreDelta)
```

### 2.5 Single-Pass Non-Double-Merge Invariant

A fundamental rule of 2048 is that **a merged tile cannot merge again within the same turn**.
Furthermore, merge precedence is strictly directed towards the movement vector.

#### Merge Truth Table & Test Cases (Sliding LEFT towards index 0)
| Input Array | Output Array | Merge Occurred? | Score Delta | Rule / Rationale |
|:---|:---|:---:|:---:|:---|
| `[2, 2, 4, 4]` | `[4, 8, 0, 0]` | Yes (2) | $+4 + 8 = 12$ | Both pairs `(2,2)` and `(4,4)` merge independently. |
| `[2, 2, 2, 0]` | `[4, 2, 0, 0]` | Yes (1) | $+4$ | Leftmost `(2,2)` merge to `4`. Third `2` slides to index 1 and **cannot** merge into the newly formed `4`. |
| `[2, 2, 2, 2]` | `[4, 4, 0, 0]` | Yes (2) | $+4 + 4 = 8$ | First pair `(2,2)` $\to$ `4` at index 0. Second pair `(2,2)` $\to$ `4` at index 1. No secondary merge into `8`. |
| `[0, 2, 0, 2]` | `[4, 0, 0, 0]` | Yes (1) | $+4$ | Empty spaces collapse, identical tiles meet and merge. |
| `[4, 2, 2, 0]` | `[4, 4, 0, 0]` | Yes (1) | $+4$ | Pair of `2`s merge into `4` at index 1. It does NOT merge into the pre-existing `4` at index 0. |
| `[2, 4, 2, 4]` | `[2, 4, 2, 4]` | No (0) | $+0$ | Alternating values, no valid merge; no empty spaces to slide into. State unchanged. |
| `[0, 0, 0, 0]` | `[0, 0, 0, 0]` | No (0) | $+0$ | All empty, no-op. |
| `[0, 0, 2, 0]` | `[2, 0, 0, 0]` | No (0) | $+0$ | Pure slide, no merge, score delta 0. |
| `[8, 4, 2, 2]` | `[8, 4, 4, 0]` | Yes (1) | $+4$ | Only trailing pair `(2,2)` merges into `4`. |
| `[2, 2, 4, 8]` | `[4, 4, 8, 0]` | Yes (1) | $+4$ | Only leading pair `(2,2)` merges into `4`. |

### 2.6 Board Transformation Matrix for 2D Grid

A full board move in direction $\mathcal{D}$ applies `compressAndMergeLine` across all parallel lines:
- For **LEFT**: Apply to rows $r \in [0..R-1]$ from left to right.
- For **RIGHT**: Apply to rows $r \in [0..R-1]$ reversed (right to left).
- For **UP**: Apply to columns $c \in [0..C-1]$ from top to bottom.
- For **DOWN**: Apply to columns $c \in [0..C-1]$ reversed (bottom to top).

#### Turn Mutation Invariant:
Let $\mathcal{G}_t$ be the grid before the move, and $\mathcal{G}'_{t+1}$ be the grid resulting from sliding and merging.
$$\text{HasChanged}(\mathcal{G}_t, \mathcal{G}'_{t+1}) = \exists (r, c) \text{ s.t. } \mathcal{G}_t(r, c) \ne \mathcal{G}'_{t+1}(r, c)$$
- **If $\text{HasChanged} == \text{false}$**: The swipe is an **invalid / no-op move**.
  - No new tile is spawned.
  - Score does not change.
  - Game state remains identical.
  - No turn counter increments.
- **If $\text{HasChanged} == \text{true}$**: The move is **valid**.
  - Score increments by $\Delta S = \sum \Delta S_{\text{lines}}$.
  - Exactly one new tile is spawned in an empty cell.
  - Turn transition is committed.

### 2.7 Obstacle & Non-Playable Cell Semantics

For progressive levels containing obstacles ($\mathcal{G}(r, c) = -1$):
1. **Impassability**: Tiles cannot move onto or through an obstacle cell.
2. **Boundary Partition**: An obstacle cell splits a row or column into independent sub-segments.
   - Example: Row `[2, 2, -1, 4, 4]` sliding LEFT:
     - Subsegment before obstacle: `[2, 2]` $\to$ `[4, 0]`
     - Obstacle remains fixed: `[-1]`
     - Subsegment after obstacle: `[4, 4]` $\to$ `[8, 0]`
     - Resulting row: `[4, 0, -1, 8, 0]`
3. **No Spawning on Obstacles**: Obstacle cells are excluded from the set of candidate spawn cells.

---

## 3. Tile Spawning Mechanics & Randomness Model

### 3.1 Spawn Trigger Invariant

A tile is spawned under exactly two circumstances:
1. **Board Initialization / Reset**: Exactly $N_{\text{init}} = 2$ tiles are spawned at randomly selected distinct empty cells.
2. **Post-Move Completion**: Exactly $1$ tile is spawned if and only if a user-initiated move resulted in $\text{HasChanged} == \text{true}$.

### 3.2 Empty Cell Selection

Let $\mathcal{E}$ be the set of empty cell coordinates:
$$\mathcal{E} = \{(r, c) \mid \mathcal{G}(r, c) == 0\}$$
If $|\mathcal{E}| = 0$, no tile can be spawned.
If $|\mathcal{E}| > 0$, an index $k \in \{0, 1, \dots, |\mathcal{E}| - 1\}$ is selected with uniform probability:
$$P(\text{Cell}_k) = \frac{1}{|\mathcal{E}|}$$

### 3.3 Value Probability Distribution (2 vs 4)

The value $V_{\text{spawn}}$ of the newly spawned tile follows a Bernoulli trial with the authoritative 2048 probability distribution:
$$P(V_{\text{spawn}} = 2) = 0.90 \quad (90\%)$$
$$P(V_{\text{spawn}} = 4) = 0.10 \quad (10\%)$$

Formally, using a uniform random float $u \sim \mathcal{U}[0, 1)$:
$$V_{\text{spawn}} = \begin{cases} 2 & \text{if } u < 0.90 \\ 4 & \text{if } u \ge 0.90 \end{cases}$$

### 3.4 Seeded PRNG for Determinism & Testability

The random number generator interface must accept an injectable seed `Random(seed: Long)`:
```kotlin
interface RandomProvider {
    fun nextInt(bound: Int): Int
    fun nextFloat(): Float
}
```
This enables:
1. Exact reproduction of game states in unit tests.
2. Replay validation for level progression.
3. Anti-cheat validation if high scores are synced.

---

## 4. Scoring & High-Score Rules

### 4.1 Score Delta Mathematical Definition

When two tiles of equal value $V$ merge, they produce a new tile of value $2V$.
The points awarded for this merge are exactly equal to the resulting tile value:
$$\Delta S_{\text{merge}} = 2V$$

Total turn score addition:
$$\Delta S_{\text{turn}} = \sum_{m \in \text{merges}} m.\text{mergedValue}$$

Examples:
- Merge $2 + 2 \to 4$: $+4$ points.
- Merge $4 + 4 \to 8$: $+8$ points.
- Merge $1024 + 1024 \to 2048$: $+2048$ points.
- Multiple merges in one swipe (e.g. $[2,2,4,4] \to [4,8,0,0]$): $+4 + 8 = +12$ points.
- Tile movement without merge: $+0$ points.

### 4.2 Game Score Accumulation

Current score $S_{t+1}$ updates atomically upon a successful move:
$$S_{t+1} = S_t + \Delta S_{\text{turn}}$$
Initial score at game start or level reset: $S_0 = 0$.

### 4.3 High Score Persistence & Real-time Update Semantics

The high score $H$ is tracked per level configuration:
$$H_{t+1} = \max(H_t, S_{t+1})$$
- As soon as $S_{t+1} > H_t$, $H$ is updated in memory and UI displays the new high score instantaneously.
- The high score is asynchronously committed to persistent storage (Jetpack DataStore / SharedPreferences) so no progress is lost on sudden process termination.

---

## 5. Game-Over & Board State Evaluation

### 5.1 Move Legality Verification Function

A swipe in direction $\vec{d}$ is legal if and only if $\text{CanMove}(\mathcal{G}, \vec{d}) == \text{true}$.
A move is legal in direction $\vec{d} = (\Delta r, \Delta c)$ if there exists at least one cell $(r, c)$ containing a tile ($\mathcal{G}(r, c) > 0$) such that:
1. The adjacent cell $(r + \Delta r, c + \Delta c)$ is inside board bounds, AND
2. The adjacent cell is empty ($\mathcal{G}(r + \Delta r, c + \Delta c) == 0$), OR
3. The adjacent cell contains a tile of identical value ($\mathcal{G}(r + \Delta r, c + \Delta c) == \mathcal{G}(r, c)$).

### 5.2 Game-Over Condition & Algorithmic Complexity

The game reaches the **GAME OVER** terminal state if and only if **no legal moves exist in any of the 4 cardinal directions**:
$$\text{IsGameOver}(\mathcal{G}) \iff \forall \vec{d} \in \{\text{UP}, \text{DOWN}, \text{LEFT}, \text{RIGHT}\}, \ \neg \text{CanMove}(\mathcal{G}, \vec{d})$$

#### Optimized Fast Evaluation ($O(R \times C)$):
```kotlin
fun isGameOver(grid: Grid): Boolean {
    // 1. If any cell is empty, game is NOT over
    for (r in 0 until grid.rows) {
        for (c in 0 until grid.cols) {
            if (grid[r, c] == 0) return false
        }
    }
    
    // 2. If board is full, check for horizontal adjacent matches
    for (r in 0 until grid.rows) {
        for (c in 0 until grid.cols - 1) {
            val v = grid[r, c]
            if (v > 0 && v == grid[r, c + 1]) return false
        }
    }
    
    // 3. Check for vertical adjacent matches
    for (c in 0 until grid.cols) {
        for (r in 0 until grid.rows - 1) {
            val v = grid[r, c]
            if (v > 0 && v == grid[r + 1, c]) return false
        }
    }
    
    // Full grid with zero adjacent matching pairs => GAME OVER
    return true
}
```

### 5.3 Board Reset & Reinitialization Lifecycle

Triggered by user tap on "Restart / Reset" or "Play Again":
1. Cancel any active animation tweens/interpolations.
2. Clear grid matrix: set all cells to $0$ (or restore level obstacle masks).
3. Reset current score $S = 0$.
4. Reset move count $M = 0$.
5. Clear undo stack (if undo feature enabled).
6. Spawn $2$ initial random tiles ($90\%$ value 2, $10\%$ value 4).
7. Preserve high score $H$.
8. Set game state to `PLAYING`.

---

## 6. Progressive Level System Specification

### 6.1 Level Progression Architecture & Game State Machine

The progressive level system provides structured gameplay goals beyond endless play.
Each level is defined by a declarative configuration:
```kotlin
data class LevelConfig(
    val levelNumber: Int,
    val name: String,
    val description: String,
    val rows: Int,
    val cols: Int,
    val targetTile: Int,             // Primary objective (e.g. 256, 512, 1024, 2048)
    val obstacles: List<Point> = emptyList(), // Cells with value -1
    val movesLimit: Int? = null,     // Optional challenge constraint
    val starThresholds: StarThresholds
)

data class StarThresholds(
    val twoStarsScore: Int,
    val threeStarsScore: Int
)
```

#### State Machine Diagram:
```
  [ LOCKED ]
      |
      | (Previous level completed)
      v
 [ UNLOCKED ] <-----------------------------------+
      |                                           |
      | (Start level)                             |
      v                                           |
  [ PLAYING ]                                     |
    /       \                                     |
   /         \                                    |
  v           v                                   |
[ GAME OVER ] [ TARGET REACHED ]                  |
  |             |                                 |
  | (Restart)   +---> "Continue" ---> [ FREE PLAY ]
  |             |
  +-------------+---> "Next Level" ---> Unlocks Level N+1
```

### 6.2 Complete Level Catalog

| Level # | Name | Grid Dimensions | Target Tile | Obstacle Coordinates | Difficulty Profile | Unlocks At |
|:---:|:---|:---:|:---:|:---:|:---|:---|
| **1** | The Spark | $4 \times 4$ | **256** | None | Gentle intro to 2048 mechanics. Fast win. | Unlocked by default |
| **2** | The Blaze | $4 \times 4$ | **512** | None | Intermediate strategy, column building. | Clear Level 1 |
| **3** | The Inferno | $4 \times 4$ | **1024** | None | Advanced tile consolidation and edge control. | Clear Level 2 |
| **4** | Classic 2048 | $4 \times 4$ | **2048** | None | The legendary classic benchmark. | Clear Level 3 |
| **5** | Tight Quarters | $3 \times 3$ | **512** | None | Extreme claustrophobia (only 9 cells total!). Highly tactical. | Clear Level 4 |
| **6** | The Monolith | $5 \times 5$ | **4096** | None | Expansive strategic space (25 cells). Deep building chains. | Clear Level 5 |
| **7** | The Vault | $4 \times 4$ | **1024** | Center blocks: `[(1,1), (2,2)]` | Obstacles split sliding lanes. Forces corner wrap tactics. | Clear Level 6 |
| **8** | The Crucible | $4 \times 4$ | **4096** | None | Master class endurance challenge. | Clear Level 7 |
| **$\infty$** | Endless Mode | User Selectable | None ($\infty$) | Configurable | Uncapped sandbox mode on any cleared grid layout. | Clear Level 4 |

### 6.3 Level Completion Triggers & Victory Modals

1. **Trigger Condition**:
   $$\text{LevelCleared} \iff \exists (r, c) \text{ s.t. } \mathcal{G}(r, c) \ge \text{targetTile}$$
2. **Immediate Freeze & Celebration**:
   - Touch input is temporarily locked.
   - Victory celebration animation (scale pop of winning tile, confetti / star particle bursts).
   - Display Level Clear Dialog:
     - Title: "Level [N] Cleared!"
     - Current Score & High Score.
     - Move count & Star Rating earned (1, 2, or 3 stars).
     - Buttons:
       - **Next Level**: Transitions to Level $N+1$.
       - **Keep Going (Free Play)**: Resumes current board without goal capping until Game Over.
       - **Replay**: Restarts Level $N$.

### 6.4 Star / Mastery Scoring System

Players earn between 1 and 3 stars per level based on performance:
- $\star$ **1 Star**: Mandatory objective met (reached `targetTile`).
- $\star\star$ **2 Stars**: Objective met AND score $S \ge \text{twoStarsScore}$.
- $\star\star\star$ **3 Stars**: Objective met AND score $S \ge \text{threeStarsScore}$.

Progressive Star Threshold Table:
| Level | Target Tile | 1 Star Threshold | 2 Stars Threshold | 3 Stars Threshold |
|:---:|:---:|:---:|:---:|:---:|
| 1 | 256 | Reaching 256 | Score $\ge 2,800$ | Score $\ge 3,500$ |
| 2 | 512 | Reaching 512 | Score $\ge 6,000$ | Score $\ge 7,500$ |
| 3 | 1024 | Reaching 1024 | Score $\ge 12,500$ | Score $\ge 16,000$ |
| 4 | 2048 | Reaching 2048 | Score $\ge 26,000$ | Score $\ge 32,000$ |
| 5 | 512 (3x3) | Reaching 512 | Score $\ge 6,200$ | Score $\ge 8,000$ |
| 6 | 4096 (5x5) | Reaching 4096 | Score $\ge 56,000$ | Score $\ge 68,000$ |
| 7 | 1024 (Vault) | Reaching 1024 | Score $\ge 13,000$ | Score $\ge 17,000$ |
| 8 | 4096 (4x4) | Reaching 4096 | Score $\ge 58,000$ | Score $\ge 70,000$ |

### 6.5 Unlock Logic & Level Selection / Replay Semantics

- **Strict Sequential Unlock**: Level 1 is unlocked initially. Level $K$ unlocks if and only if Level $K-1$ has been completed (`isCompleted == true`).
- **Level Select Screen**:
  - Grid or Carousel view of all levels.
  - Locked levels display a padlock icon and the unlock condition ("Clear Level N-1").
  - Unlocked levels display: Level Name, Grid Size, Target Tile, Stars Earned (0-3), and Personal Best Score.
- **Independent Replay**: Replaying a completed level never revokes downstream unlocks. High scores and stars are updated monotonically:
  $$\text{savedBestScore} = \max(\text{previousBest}, \text{newScore})$$
  $$\text{savedStars} = \max(\text{previousStars}, \text{newStars})$$

### 6.6 Persistence Schema (DataStore / SharedPreferences)

To satisfy `ORIGINAL_REQUEST.md` requirement R2 ("Persist level unlock progress across app restarts") with zero external bloat:

```json
{
  "activeLevelNumber": 1,
  "globalHighScore": 34820,
  "levels": {
    "1": {
      "isUnlocked": true,
      "isCompleted": true,
      "bestScore": 3840,
      "bestTile": 256,
      "starsEarned": 3
    },
    "2": {
      "isUnlocked": true,
      "isCompleted": false,
      "bestScore": 1240,
      "bestTile": 128,
      "starsEarned": 0
    },
    "3": {
      "isUnlocked": false,
      "isCompleted": false,
      "bestScore": 0,
      "bestTile": 0,
      "starsEarned": 0
    }
  },
  "savedGame": {
    "levelNumber": 2,
    "score": 1240,
    "board": [
      [0, 2, 4, 8],
      [16, 32, 64, 128],
      [0, 0, 4, 2],
      [0, 0, 0, 0]
    ]
  }
}
```

#### Persistence Rules:
1. **Atomic Commits**: Save operations must use asynchronous atomic file writes (`apply()` in SharedPreferences or Proto/Preferences DataStore) to guarantee data integrity across process kills.
2. **Resume Capability**: When the app launches, if `savedGame` exists for `activeLevelNumber` and is not in Game Over state, prompt or resume the board state immediately.

---

## 7. Fluid Animation & 60+ FPS Touch UX Specification

### 7.1 Decoupled State & Animation Event Pipeline

To achieve fluid, stutter-free 60+ FPS (or 90/120Hz on modern Android displays), game logic evaluation is completely decoupled from rendering:

```
[Touch Gesture Detected]
         |
         v
[Game Engine Core: Pure Function]
         |
         v
Returns MoveResult:
  - previousGridState
  - finalGridState
  - scoreDelta
  - slideAnimations: List<SlideEvent(tileId, from(r,c), to(r,c))>
  - mergeAnimations: List<MergeEvent(tile1Id, tile2Id, newTileId, target(r,c), value)>
  - spawnAnimation: SpawnEvent(newTileId, at(r,c), value)
         |
         v
[Animation Orchestrator / AnimatorSet]
         |
         v
[Render Pipeline: Custom View or Compose Canvas]
```

### 7.2 Movement Vector Interpolation (Slide Offset)

- **Duration**: $100\text{ms} - 120\text{ms}$
- **Interpolator**: Fast-Out Slow-In (Cubic Bezier $(0.4, 0.0, 0.2, 1.0)$) or `DecelerateInterpolator(1.5f)`
- **Formula**:
  For progress $t \in [0.0, 1.0]$:
  $$\text{offset}_x(t) = \text{start}_x + (\text{end}_x - \text{start}_x) \cdot \text{Interp}(t)$$
  $$\text{offset}_y(t) = \text{start}_y + (\text{end}_y - \text{start}_y) \cdot \text{Interp}(t)$$

### 7.3 Merge Pop Dynamics (Overshoot Curve)

When two tiles meet at the destination cell, the merged tile is rendered with a scale bounce:
- **Duration**: $100\text{ms} - 130\text{ms}$
- **Trigger**: Starts at the exact moment the slide animation reaches $t = 1.0$ (or slightly overlapping at $t = 0.85$).
- **Interpolator**: `OvershootInterpolator(tension = 2.0f)`
- **Scale Range**: $1.0 \to 1.25 \to 1.0$
- **Mathematical Curve**:
  $$\text{Scale}(t) = 1.0 + 0.25 \cdot \sin(\pi \cdot t) \quad \text{for } t \in [0.0, 1.0]$$

### 7.4 Spawn Appearance (Scale & Alpha Curves)

Newly spawned tiles scale up from the center of their cell while fading in:
- **Duration**: $100\text{ms} - 140\text{ms}$
- **Trigger**: Concurrently with merge pop, immediately after sliding terminates.
- **Scale Curve**: $0.0 \to 1.0$ using `DecelerateInterpolator`
- **Alpha Curve**: $0.0 \to 1.0$ linear or decelerate.
- **Formula**:
  $$\text{Scale}_{\text{spawn}}(t) = t \cdot (2 - t)$$
  $$\text{Alpha}_{\text{spawn}}(t) = t$$

### 7.5 Timing Budget & Orchestration Timeline

To guarantee total responsiveness, the combined turn animation must never exceed $220\text{ms}$:

```
Timeline (ms):
0ms         80ms   100ms       140ms       200ms
|------------|-------|-----------|-----------|
[==== Slide ====]
             [===== Merge Pop =====]
             [====== Spawn In ======]
```

### 7.6 Touch Gesture Detection & Input Queueing / Fast-Forward

#### Gesture Recognition Spec:
1. **Touch Down**: Record origin point $(x_0, y_0)$ and timestamp $t_0$.
2. **Touch Move / Up**: Calculate displacement $\Delta x = x_1 - x_0$, $\Delta y = y_1 - y_0$.
3. **Thresholds**:
   - Minimum swipe distance: $d_{\text{min}} = 24\text{dp}$ (approximately $48\text{px}-72\text{px}$ on standard densities).
   - Angle Resolution: Direction is determined by the dominant axis:
     $$\text{Direction} = \begin{cases}
     \text{RIGHT} & \text{if } \Delta x > 0 \text{ and } |\Delta x| \ge |\Delta y| \\
     \text{LEFT}  & \text{if } \Delta x < 0 \text{ and } |\Delta x| \ge |\Delta y| \\
     \text{DOWN}  & \text{if } \Delta y > 0 \text{ and } |\Delta y| > |\Delta x| \\
     \text{UP}    & \text{if } \Delta y < 0 \text{ and } |\Delta y| > |\Delta x|
     \end{cases}$$

#### Input Buffering & Fast-Forward Rule:
If the user swipes rapidly while a slide/merge animation is currently playing:
1. **Fast-Forward**: Immediately snap the ongoing animation to its final state ($t = 1.0$).
2. **Process Queued Move**: Evaluate the incoming swipe instantaneously without dropping the user's gesture.
3. **Buffer Limit**: Maximum queue depth is 1 move. Rapid accidental flurries beyond 1 pending move are discarded to prevent chaotic runaway moves.

### 7.7 Render Pipeline & Zero-Allocation onDraw Contracts

To guarantee consistent 60+ FPS without garbage collection (GC) stutters:
1. **Zero Object Allocation in Render Loop**:
   - `Paint`, `RectF`, `Path`, `Matrix`, and typography measure objects are instantiated once during view initialization or `onSizeChanged()`.
   - Never instantiate objects (`new Paint()`, `RectF()`, `String.format()`, etc.) inside `onDraw()`.
2. **Hardware Acceleration**:
   - Ensure `setLayerType(View.LAYER_TYPE_HARDWARE, null)` or standard hardware-accelerated Canvas is active.
3. **Adaptive Typography**:
   - Font size scales dynamically with tile value digit count (2-digit vs 4-digit vs 5-digit) to prevent text clipping inside cells.

---

## 8. Features Discovered Catalog

The following table documents all features discovered, formalized, and probed across the specification sources (`ORIGINAL_REQUEST.md` and reference 2048 mechanics):

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|:---:|:---|:---|:---|:---|:---|:---|:---|
| 1 | Core Engine | Grid Representation | 2D matrix structure ($R \times C$) supporting variable dimensions ($3 \times 3$, $4 \times 4$, $5 \times 5$). | Row count $R$, Col count $C$ | Instantiated grid matrix with empty/obstacle cells | Reject dimensions $< 2$ or $> 8$ | ORIGINAL_REQUEST R1, R2 |
| 2 | Core Engine | Unique Tile Tracking | Unique 64-bit ID assigned to each tile instance for animation interpolation. | Tile value, position $(r, c)$ | `Tile(id, value, r, c)` | Auto-increment collision prevention | UI/UX Fluid Animation reqs |
| 3 | Core Engine | 4-Direction Swipe | Translates directional swipe into matrix transformations along cardinal vectors. | Swipe Direction: UP, DOWN, LEFT, RIGHT | New board state, move list | Invalid direction ignored | ORIGINAL_REQUEST R1 |
| 4 | Core Engine | 1D Slide Compression | Compresses non-empty cells towards boundary, eliminating gaps. | Array of tiles/empty cells | Compacted array | Preserves obstacle bounds | 2048 canonical specification |
| 5 | Core Engine | Single-Pass Merge | Merges adjacent equal tiles in single pass; prevents newly merged tiles from re-merging. | Compacted line | Merged line, merge events, score delta | Idempotent on unmergeable lines | ORIGINAL_REQUEST R1, Canonical Spec |
| 6 | Core Engine | Move Mutation Guard | Disallows turns where board state does not mutate (no slide, no merge). | $\mathcal{G}_t$, $\mathcal{G}_{t+1}$ | Boolean `hasChanged` | Ignores no-op swipes; suppresses tile spawn | Canonical 2048 Invariant |
| 7 | Core Engine | Empty Cell Spawn | Spawns single tile in randomly selected unoccupied cell upon valid move. | Grid $\mathcal{G}$, PRNG | Grid with new tile at $(r, c)$ | No spawn if grid is full or no move made | ORIGINAL_REQUEST R1 |
| 8 | Core Engine | 90/10 Value Distribution | Spawns value 2 with $90\%$ probability, value 4 with $10\%$ probability. | Uniform float $u \in [0, 1)$ | Tile value 2 or 4 | Fallback to 2 if PRNG out of bounds | Canonical 2048 Invariant |
| 9 | Core Engine | Turn Score Accumulation | Awards points equal to the face value of newly merged tiles. | List of merge events | Turn score delta $\Delta S$ | Negative or null values rejected | ORIGINAL_REQUEST R1 |
| 10 | Core Engine | Real-time High Score | Dynamically tracks and updates highest score achieved. | Current score $S$, High score $H$ | Updated $H = \max(H, S)$ | Non-decreasing invariant | ORIGINAL_REQUEST R1, AC |
| 11 | Core Engine | Game-Over Detection | Detects when board is full and no valid adjacent merges exist. | Grid state $\mathcal{G}$ | Boolean `isGameOver` | Early exit on first empty cell found ($O(RC)$) | ORIGINAL_REQUEST R1, AC |
| 12 | Core Engine | Board Reset | Resets grid to empty, clears score, respawns 2 initial tiles, preserves high score. | Reset trigger | Fresh board state | State reset atomic | ORIGINAL_REQUEST R1, AC |
| 13 | Level System | Escalating Goal Tiers | Escalating objectives: 256, 512, 1024, 2048, 4096. | Level ID | Target tile threshold | Unrecognized ID defaults to Level 1 | ORIGINAL_REQUEST R2 |
| 14 | Level System | Multi-Grid Layouts | Support for $3 \times 3$ (Tight Quarters) and $5 \times 5$ (Monolith) boards. | Level config | Dimensioned grid | Invalid dimensions throw ConfigException | ORIGINAL_REQUEST R2 |
| 15 | Level System | Obstacle Cells | Fixed impassable blocks (value $-1$) that act as barriers. | Obstacle coordinate list | Partitioned grid lanes | Overlapping obstacle bounds validated | ORIGINAL_REQUEST R2 |
| 16 | Level System | Level Win Trigger | Triggers victory state immediately when any tile reaches target value. | Grid state, target value | LevelCleared event | Triggered only once per level session | ORIGINAL_REQUEST R2, AC |
| 17 | Level System | Level Unlock Progression | Unlocks Level $N+1$ when Level $N$ is completed. | Level $N$ completion | Level $N+1$ unlocked status | Cannot skip locked levels | ORIGINAL_REQUEST R2, AC |
| 18 | Level System | Level Selection Screen | Menu displaying all levels, lock state, stars, and best scores. | Persistence store | Rendered level list | Disabled clicks on locked levels | ORIGINAL_REQUEST AC |
| 19 | Level System | Level Replayability | Allows replaying cleared levels without losing unlock progress. | Level select action | Fresh session for selected level | Preserves high score and stars | ORIGINAL_REQUEST AC |
| 20 | Level System | Star Rating System | Awards 1 to 3 stars based on score thresholds per level. | Final level score, thresholds | Star count (1, 2, or 3) | Min 1 star on win | Gameplay Design Spec |
| 21 | Persistence | State Serialization | Persists level unlock state, high scores, and active game across app restarts. | Game state object | Serialized preferences / JSON | Corrupt file triggers fallback to defaults | ORIGINAL_REQUEST R2, AC |
| 22 | Animation | Slide Interpolation | Smooth position translation of moving tiles over $100\text{ms}-120\text{ms}$. | Start pos, End pos, elapsed time | Current pixel coordinates | Clamped to $[0.0, 1.0]$ | ORIGINAL_REQUEST R1, AC |
| 23 | Animation | Merge Pop Effect | Overshoot scale bounce ($1.0 \to 1.25 \to 1.0$) upon tile collision. | Merge timestamp, duration | Current scale factor | Smooth decay, no overshoot distortion | ORIGINAL_REQUEST R1, AC |
| 24 | Animation | Spawn Fade/Scale | Fade-in and scale-in ($0.0 \to 1.0$) for newly created tiles. | Spawn timestamp, duration | Current alpha & scale | Clamped to $1.0$ | ORIGINAL_REQUEST R1, AC |
| 25 | UX / Touch | Swipe Gesture Detector | Classifies touch drags exceeding $24\text{dp}$ into 4 cardinal directions. | Touch MotionEvents | Direction enum | Discards gestures below threshold | ORIGINAL_REQUEST AC |
| 26 | UX / Touch | Input Buffer / Fast-Forward | Snaps playing animations to completion if rapid swipe received. | Queued swipe event | Fast-forwarded frame + immediate move | Queue depth capped at 1 | Fluid 60+ FPS reqs |
| 27 | Rendering | Zero-Allocation Draw | Reusable paint/rect objects in custom view to avoid GC jitter at 60+ FPS. | Render loop calls | Rendered canvas frame | Static allocations verified | ORIGINAL_REQUEST R1, R3 |
| 28 | Endless Mode | Free Play Continuation | Option to continue playing past target tile without goal restriction. | "Keep Going" user tap | Uncapped play session | Terminates only on Game Over | Progressive System Spec |

---

## 9. Comprehensive Edge Cases & Boundary Conditions

| # | Feature | Input Scenario | Expected / Observed Behavior | Validation Verification |
|:---:|:---|:---|:---|:---|
| 1 | Single-Pass Merge | Line `[2, 2, 2, 2]` sliding LEFT | Yields `[4, 4, 0, 0]`, score $+8$. Does NOT merge into `[8, 0, 0, 0]`. | Unit test with exact vector comparison. |
| 2 | Triple Tile Merge | Line `[2, 2, 2, 0]` sliding LEFT | Yields `[4, 2, 0, 0]`, score $+4$. Leftmost pair merges, remaining single tile slides adjacent. | Assert index 0 is 4, index 1 is 2. |
| 3 | Embedded Gap Merge | Line `[2, 0, 0, 2]` sliding LEFT | Yields `[4, 0, 0, 0]`, score $+4$. Empty cells eliminated before merge check. | Assert index 0 is 4, others 0. |
| 4 | No-Op Move | Full line `[2, 4, 8, 16]` sliding LEFT | Yields `[2, 4, 8, 16]`, score $+0$. `HasChanged == false`. No tile spawned. | Assert grid reference equal and spawn count 0. |
| 5 | Full Board No Moves | 4x4 grid with alternating values and no adjacent matches | `isGameOver() == true`. Swipe gestures ignored. Game over modal rendered. | Assert game state is `GAME_OVER`. |
| 6 | Full Board with Move | 4x4 grid full, but cell `(3,2) == 4` and `(3,3) == 4` | `isGameOver() == false`. Swiping LEFT/RIGHT executes merge and creates empty space. | Move succeeds, game continues. |
| 7 | Obstacle Blocking | Line `[2, 2, -1, 4, 4]` sliding LEFT | Yields `[4, 0, -1, 8, 0]`, score $+12$. Obstacle `-1` stays at index 2; splits merge domains. | Assert index 2 is -1. |
| 8 | Tile Collision with Obstacle | Line `[0, 2, -1, 0, 0]` sliding RIGHT | Yields `[0, 0, -1, 0, 2]`. Tile before obstacle slides up to obstacle: `[0, 2, -1, ...]`. | Assert tile cannot cross obstacle boundary. |
| 9 | Rapid Consecutive Swipes | User swipes LEFT then immediately UP within 30ms | Animation 1 snaps to completion; Move 2 executes seamlessly without dropped inputs. | Input buffer depth 1 verified. |
| 10 | Level Target Met on Last Move | Tile reaches target value simultaneously when board becomes full | Victory condition evaluated **before** game over. Player wins level! | Level clear modal takes precedence over game over. |
| 11 | Process Death Mid-Game | OS terminates app in background during active level | On relaunch, saved grid, current score, and level progression restored accurately. | Kill process test with JSON/DataStore verification. |
| 12 | App Launch Cold Start | Fresh install without saved preferences | App initializes Level 1 unlocked, Levels 2-8 locked, high score 0. | Fresh state verification. |
| 13 | Replay Completed Level | User replays Level 1 and gets lower score | Level 2 remains unlocked; Level 1 high score and stars remain at maximum historical values. | Monotonic high score verification. |
| 14 | Small Screen (3x3 Grid) | Level 5 initialization on small 3x3 board | Board renders with 9 cells, 2 initial tiles spawned, game over correctly evaluates 3x3 matrix. | Verify matrix bounds in loop. |
| 15 | Large Screen (5x5 Grid) | Level 6 initialization on large 5x5 board | Board renders with 25 cells, font sizes adapt to maintain readability. | Visual and coordinate verification. |
| 16 | Diagonal Swipes | User drags finger at $45^\circ$ angle | Dominant axis displacement ($|\Delta x|$ vs $|\Delta y|$) resolves tie deterministically. | Tie-break rule verification. |

---

## 10. Verification Criteria & Acceptance Tests

The downstream implementation must pass the following test suites with 100% code coverage on the core logic:

### Test Suite 1: Pure 1D Line Operations (`LineCompressorTest`)
- `testEmptyLineRemainsEmpty()`
- `testSingleTileSlidesToEdge()`
- `testTwoIdenticalTilesMerge()`
- `testTwoDifferentTilesDoNotMerge()`
- `testFourIdenticalTilesMergeInPairs()`: `[2,2,2,2]` $\to$ `[4,4,0,0]`
- `testThreeIdenticalTilesMergeLeadingPair()`: `[2,2,2,0]` $\to$ `[4,2,0,0]`
- `testObstacleSplitsMergeDomain()`: `[2,2,-1,4,4]` $\to$ `[4,0,-1,8,0]`

### Test Suite 2: 2D Grid Engine (`GridEngineTest`)
- `testMoveInAllFourDirections()`: Verifies matrix transposition/reflection accuracy.
- `testInvalidMoveDoesNotSpawnTile()`: Swipe against wall does not alter state.
- `testValidMoveSpawnsExactlyOneTile()`: Count of non-empty cells increases by $1 - \text{merges}$.
- `testScoreAccumulationAccurate()`: Score equals exact sum of merged values.
- `testGameOverDetectionFullNoMoves()`: Full grid with zero matches triggers game over.
- `testGameOverDetectionFullWithMoves()`: Full grid with matches does not trigger game over.

### Test Suite 3: Progressive Level Engine (`LevelManagerTest`)
- `testLevel1InitialState()`: Level 1 unlocked, target 256.
- `testLevelCompletionUnlocksNextLevel()`: Achieving target tile unlocks level $N+1$.
- `testLevelPersistenceAcrossReload()`: State saved to disk, reloaded accurately.
- `testLevelReplayDoesNotResetProgress()`: High score monotonic update.

---
*End of Specification Document `spec_mechanics.md`*
