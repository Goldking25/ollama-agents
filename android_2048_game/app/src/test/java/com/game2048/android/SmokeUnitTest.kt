package com.game2048.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Baseline smoke unit test verifying JUnit test runner execution in pure JVM.
 */
class SmokeUnitTest {

    @Test
    fun testJUnitRunnerExecution() {
        val expected = 2048
        val calculated = 1024 * 2
        assertEquals("Multiplication of 1024 by 2 should equal 2048", expected, calculated)
    }

    @Test
    fun testBasicMathAssertions() {
        val base = 2
        var value = base
        for (i in 1..10) {
            value *= 2
        }
        assertEquals(2048, value)
        assertTrue(value > 0)
    }
}
