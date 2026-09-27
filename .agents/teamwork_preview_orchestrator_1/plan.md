# Orchestration Plan: Android 2048 Game App

## Objectives
Deliver a lightweight, highly responsive, production-quality Android 2048 game app in `e:\Learning\Python\agent_test\android_2048_game` matching all criteria in `ORIGINAL_REQUEST.md`:
- Core 2048 gameplay (sliding in 4 directions, merges, edge collision, score accumulation, board reset, game over detection).
- Fluid animations (slide offset, merge pop, spawn fade/scale) at 60+ FPS touch responsiveness.
- Progressive Level System (escalating challenges/targets/layouts, smooth unlock transitions, persistence, replay/selection).
- Android Compatibility: minSdkVersion <= 31 (Android 12), targetSdkVersion >= 35 (Android 15).
- Ultra-lean binary footprint: Release APK < 5 MB via vector drawables, zero redundant assets, R8 code/resource shrinking.
- Comprehensive automated test suite passing 100% and audited for full integrity.

## Phase Breakdown

### Phase 0: Survey & Environment Assessment
- Dispatch 3 parallel survey subagents:
  - `survey_spec_mechanics`: Extract detailed specifications for gameplay mechanics, animations, gestures, and level progression rules.
  - `survey_architecture`: Evaluate Android architectural patterns, lightweight UI approaches (Custom View vs Jetpack Compose vs SurfaceView for ultra-lean APK & 60+ FPS), persistence, and R8 configuration.
  - `survey_environment`: Inspect the host environment (Java, Kotlin, Android SDK, build-tools, platform-tools, gradle) to establish build/test command capabilities.
- Aggregate findings into `PROJECT.md` with a complete Feature Inventory and Interface Contracts.

### Phase 1: Decomposition & Dual Track Setup
- Formulate milestone plan in `PROJECT.md`:
  - Milestone 1: Android Project Setup, Gradle Build Configuration, Toolchain & SDK setup (minSdk 31, targetSdk 35, Proguard/R8 setup).
  - Milestone 2: Core 2048 Engine & Math Model (grid, sliding, merging, spawning, scoring, state machine) + pure unit tests.
  - Milestone 3: Progressive Level System & Persistence (escalating goals, grid configurations, unlock state, DataStore/SharedPreferences persistence).
  - Milestone 4: Fluid Animation & Custom View UI / Touch Gesture Handling (swipe detector, smooth 60+ FPS rendering, slide/pop/spawn animations, responsive layout).
  - Milestone 5: Level Selection UI, Audio/Haptics (if applicable) & Game Over/Victory Overlays.
  - Milestone 6: APK Size Optimization & Build Hardening (< 5 MB release verification).
- Setup E2E Testing Track to produce requirement-driven test suite (Tiers 1-4) and publish `TEST_READY.md`.

### Phase 2: Execution & Sub-Orchestration
- Dispatch sub-orchestrators for milestones adhering to dependency ordering.
- For each milestone: Explorer -> Worker -> Reviewers (2) -> Challengers (2) -> Auditor.
- Binary veto on Forensic Auditor violations. Clean gate pass required.

### Phase 3: Final Integration Milestone & Adversarial Hardening
- Phase 1: Run 100% of E2E test suite (Tiers 1-4). Fix any discrepancies.
- Phase 2: Tier 5 Adversarial Coverage Hardening with Challengers.

### Phase 4: Final Handshake & Delivery Report
- Run final release build, verify APK size < 5 MB, inspect test reports.
- Deliver full completion report to Sentinel.
