# Project: Android 2048 Game App

## Architecture
- **Language**: Kotlin 2.0.21, Java 21 LTS
- **Build System**: Gradle 8.10.2 with Android Gradle Plugin (AGP) 8.7.2
- **OS Compatibility**: `minSdkVersion` 31 (Android 12), `targetSdkVersion` 35 (Android 15), `compileSdk` 35
- **UI Architecture**: Single Activity (`MainActivity`) + High-performance 2D Canvas Custom View (`GameBoardView`) with hardware acceleration and zero allocation in `onDraw()`.
- **Animation Architecture**: Two-phase `ValueAnimator` pipeline: 120ms slide (`DecelerateInterpolator`) followed by 100ms merge-pop / spawn (`OvershootInterpolator`), total turnaround <= 220ms, with input queueing and fast-forward capability for 60+ FPS touch responsiveness.
- **State & Persistence**: Decoupled pure Kotlin domain layer (`GameEngine`, `LevelController`) with lightweight `SharedPreferences` + platform `org.json` persistence (0 KB library bloat).
- **Binary Footprint Strategy**: Release build with R8 full-mode shrinking, resource shrinking, Proguard optimization, vector drawables only, zero native C++ (.so) libraries (inherent 16 KB page-size compliance for Android 15), release APK strictly < 5 MB (target ~1.2 MB – 1.8 MB).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Project Scaffolding & Toolchain | Gradle 8.10.2, AGP 8.7.2, minSdk 31, targetSdk 35, local.properties, gradle.properties | M1 | ORIGINAL_REQUEST §R3 |
| F02 | Deterministic Grid Representation | 2D/1D grid model supporting arbitrary dimensions (3x3, 4x4, 5x5) and obstacles (-1) | M2 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F03 | 1D/2D Slide & Merge Algorithm | Canonical single-pass non-double-merge invariant (`[2,2,4,4]->[4,8,0,0]`, `[2,2,2,0]->[4,2,0,0]`) | M2 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F04 | Score Accumulation Engine | Real-time score computation ($\Delta S = \text{sum of merged tile values}$) | M2 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F05 | Deterministic Tile Spawning | Bernoulli 90%/10% (2 vs 4), empty cell selection, seedable PRNG interface, spawns only on move | M2 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F06 | Game-Over Detection | $O(RC)$ evaluation for zero empty cells and no adjacent horizontal/vertical equal tiles | M2 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F07 | Board Reset & State Transitions | Transitions across IDLE, PLAYING, LEVEL_WON, GAME_OVER states | M2 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F08 | Progressive Level Catalog | 8-level curriculum (L1 4x4/256 to L4 2048, L5 3x3, L6 5x5, L7 Obstacles, L8 4096) + Endless | M3 | ORIGINAL_REQUEST §R2, spec_mechanics |
| F09 | Star Rating System | 1-to-3 star performance rating based on move efficiency and score thresholds | M3 | ORIGINAL_REQUEST §R2, spec_mechanics |
| F10 | Objective Evaluator & Unlocks | Level completion trigger, monotonic unlock of subsequent level, victory transition | M3 | ORIGINAL_REQUEST §R2, spec_mechanics |
| F11 | Lightweight Persistence Engine | SharedPreferences + org.json for high scores, active level, unlock set, star ratings, saved game | M3 | ORIGINAL_REQUEST §R2, spec_architecture |
| F12 | Level Selection & Replay | Ability to select unlocked levels, replay completed levels, record high scores monotonically | M3 | ORIGINAL_REQUEST §R2, spec_mechanics |
| F13 | Canvas 2D Custom View Engine | `GameBoardView` with hardware acceleration, zero allocation in `onDraw()`, color palette | M4 | ORIGINAL_REQUEST §R1, spec_architecture |
| F14 | Two-Phase Animation Pipeline | 120ms slide + 100ms pop/spawn, interpolators, <=220ms budget, input queueing & fast-forward | M4 | ORIGINAL_REQUEST §R1, spec_mechanics |
| F15 | 4-Direction Swipe Gesture Detector | `GestureDetector.SimpleOnGestureListener` detecting UP, DOWN, LEFT, RIGHT accurately | M4 | ORIGINAL_REQUEST §R1, spec_architecture |
| F16 | Responsive Layout & HUD | XML layout with score, best score, level badge, reset/level buttons, WindowInsetsCompat | M4 | ORIGINAL_REQUEST §R3, spec_architecture |
| F17 | Level Clear & Game Over Overlays | Polished dialogs for Level Clear (stars, next level, replay) and Game Over (try again, reset) | M5 | ORIGINAL_REQUEST §R1-R2 |
| F18 | Level Selection Dialog / UI | Interactive grid/list dialog to choose any unlocked level with star ratings | M5 | ORIGINAL_REQUEST §R2 |
| F19 | Vector Assets & Theme Styling | Clean vector drawables for icons, buttons, badges (zero PNG/JPG bloat) | M5 | ORIGINAL_REQUEST §R3 |
| F20 | R8 Shrinking & ProGuard Hardening | Code shrinking, resource shrinking, Proguard rules, release APK build under 5 MB | M6 | ORIGINAL_REQUEST §R3, spec_architecture |
| F21 | Pure JVM Domain Unit Test Suite | Deterministic JUnit 4/5 tests for 100% of game math, merge truth tables, and level rules | M2-M3 | ORIGINAL_REQUEST Acceptance Criteria |
| F22 | E2E Integration Test Suite | Opaque-box automated test suite (Tiers 1-4) covering all features and user scenarios | E2E Track | ORIGINAL_REQUEST Acceptance Criteria |
| F23 | Adversarial Coverage Hardening | White-box stress testing, corner cases, and boundary exploration (Tier 5) | Final M | Iteration Loop Specification |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Project Scaffolding & Build Toolchain | Project scaffolding, Gradle 8.10.2, AGP 8.7.2, minSdk 31, targetSdk 35, local.properties | none | DONE |
| M2 | Core 2048 Engine & Math Domain | Grid representation, single-pass merge, scoring, PRNG spawn, game over, unit tests | M1 | IN_PROGRESS |
| M3 | Progressive Level System & Persistence | 8 levels + Endless, star ratings, unlock progression, SharedPreferences/JSON persistence | M2 | PLANNED |
| M4 | Canvas UI Engine, Animations & Gestures | `GameBoardView`, 2-phase animations, gesture detector, HUD layout, edge-to-edge | M3 | PLANNED |
| M5 | Level Select UI, Overlays & Vector Assets | Level select dialog, victory/game-over overlays, vector assets, adaptive styling | M4 | PLANNED |
| M6 | Build Hardening & Release Optimization | R8 full-mode shrinking, Proguard rules, `assembleRelease`, APK size < 5 MB verification | M5 | PLANNED |
| Final | E2E Verification & Adversarial Hardening | Phase 1: 100% E2E test pass (Tiers 1-4); Phase 2: Tier 5 Challenger adversarial hardening | M6, E2E Track | PLANNED |
