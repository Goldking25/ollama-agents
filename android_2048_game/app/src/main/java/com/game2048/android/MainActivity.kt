package com.game2048.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.game2048.android.core.engine.GameEngineImpl
import com.game2048.android.core.model.GameState
import com.game2048.android.core.model.MoveDirection
import kotlin.math.abs

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFFFAF8EF)
                ) {
                    GameScreen()
                }
            }
        }
    }
}

@Composable
fun GameScreen() {
    // Engine reference (survives recompositions)
    val engine = remember { GameEngineImpl().apply { startNewGame() } }
    
    // We use a simple integer state to trigger recomposition when board changes
    var trigger by remember { mutableStateOf(0) }
    
    val currentScore = engine.score
    val bestScore = engine.highScore
    val gameState = engine.gameState
    
    // Copy the grid values into an immutable structure for rendering
    val gridRows = engine.grid.rows
    val gridCols = engine.grid.cols
    val boardData = Array(gridRows) { r ->
        IntArray(gridCols) { c ->
            engine.grid.getValue(r, c)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("2048", fontSize = 48.sp, fontWeight = FontWeight.Bold, color = Color(0xFF776E65))
            
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ScoreBox("SCORE", currentScore)
                ScoreBox("BEST", bestScore)
            }
        }
        
        Spacer(modifier = Modifier.height(16.dp))
        
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Join the numbers!", color = Color(0xFF776E65))
            Button(
                onClick = {
                    engine.startNewGame()
                    trigger++
                },
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF8F7A66))
            ) {
                Text("New Game")
            }
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        // Game Board
        Box(
            modifier = Modifier
                .aspectRatio(1f)
                .background(Color(0xFFBBADA0), RoundedCornerShape(8.dp))
                .padding(8.dp)
                .pointerInput(Unit) {
                    var swiped = false
                    detectDragGestures(
                        onDragStart = { swiped = false },
                        onDragEnd = { swiped = false },
                        onDragCancel = { swiped = false }
                    ) { change, dragAmount ->
                        change.consume()
                        if (swiped) return@detectDragGestures
                        val (x, y) = dragAmount
                        if (abs(x) > abs(y)) {
                            // Horizontal
                            if (abs(x) > 20) { // Threshold
                                val dir = if (x > 0) MoveDirection.RIGHT else MoveDirection.LEFT
                                val result = engine.move(dir)
                                if (result.moved) trigger++
                                swiped = true
                            }
                        } else {
                            // Vertical
                            if (abs(y) > 20) { // Threshold
                                val dir = if (y > 0) MoveDirection.DOWN else MoveDirection.UP
                                val result = engine.move(dir)
                                if (result.moved) trigger++
                                swiped = true
                            }
                        }
                    }
                }
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxSize()
            ) {
                for (r in 0 until gridRows) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.weight(1f).fillMaxWidth()
                    ) {
                        for (c in 0 until gridCols) {
                            val value = boardData[r][c]
                            Tile(
                                value = value,
                                modifier = Modifier.weight(1f).fillMaxHeight()
                            )
                        }
                    }
                }
            }
            
            // Overlays
            if (gameState == GameState.GAME_OVER) {
                Overlay("Game Over!", engine, { trigger++ })
            } else if (gameState == GameState.LEVEL_WON && !engine.isFreePlay) {
                Overlay("You Win!", engine, { trigger++ }, showContinue = true)
            }
        }
    }
}

@Composable
fun Overlay(text: String, engine: GameEngineImpl, onTrigger: () -> Unit, showContinue: Boolean = false) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0x88FFFFFF), RoundedCornerShape(8.dp)),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(text, fontSize = 48.sp, fontWeight = FontWeight.Bold, color = Color(0xFF776E65))
            Spacer(modifier = Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Button(
                    onClick = {
                        engine.startNewGame()
                        onTrigger()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF8F7A66))
                ) {
                    Text("Try again")
                }
                
                if (showContinue) {
                    Button(
                        onClick = {
                            engine.continuePlaying()
                            onTrigger()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF8F7A66))
                    ) {
                        Text("Keep going")
                    }
                }
            }
        }
    }
}

@Composable
fun ScoreBox(label: String, score: Int) {
    Column(
        modifier = Modifier
            .background(Color(0xFFBBADA0), RoundedCornerShape(4.dp))
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(label, color = Color(0xFFEEE4DA), fontSize = 10.sp, fontWeight = FontWeight.Bold)
        Text(score.toString(), color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun Tile(value: Int, modifier: Modifier) {
    val bgColor = when (value) {
        0 -> Color(0xFFCDC1B4)
        2 -> Color(0xFFEEE4DA)
        4 -> Color(0xFFEDE0C8)
        8 -> Color(0xFFF2B179)
        16 -> Color(0xFFF59563)
        32 -> Color(0xFFF67C5F)
        64 -> Color(0xFFF65E3B)
        128 -> Color(0xFFEDCF72)
        256 -> Color(0xFFEDCC61)
        512 -> Color(0xFFEDC850)
        1024 -> Color(0xFFEDC53F)
        2048 -> Color(0xFFEDC22E)
        else -> Color(0xFF3C3A32)
    }
    
    val textColor = if (value <= 4) Color(0xFF776E65) else Color.White
    
    Box(
        modifier = modifier
            .background(bgColor, RoundedCornerShape(4.dp)),
        contentAlignment = Alignment.Center
    ) {
        if (value > 0) {
            val fontSize = if (value < 100) 36.sp else if (value < 1000) 30.sp else 24.sp
            Text(
                text = value.toString(),
                color = textColor,
                fontSize = fontSize,
                fontWeight = FontWeight.Bold
            )
        }
    }
}
