from flask import Flask, render_template_string
import os
app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Balls Animation (WEBGL2 Physics simulator)</title>
<style>
body { margin:0; overflow:hidden; background:#111; touch-action:none; }
canvas { display:block; }
#info { 
    position:absolute; top:10px; left:10px; 
    color:#fff; font-family:monospace; font-size:12px; 
    z-index:10; background:rgba(0,0,0,0.5); 
    padding:8px; border-radius:4px;
}
#info span { color:#0f0; }
</style>
</head>
<body>
<canvas id="canvas"></canvas>
<div id="info">
    <div id="controls" style="cursor:pointer;user-select:none;">
        <span class="control-btn" data-key="g">G: gravity</span> | 
        <span class="control-btn" data-key="r">R: reset</span> | 
        <span class="control-btn" data-key="m">M: mute</span> | 
        <span class="control-btn" data-key="o">O: Obama</span> | 
        <span class="control-btn" data-key="t">T: Trump</span> | 
        <span class="control-btn" data-key=" ">SPACE: +100</span>
    </div>
    <div>Balls: <span id="ballCount">10</span> | FPS: <span id="fps">60</span></div>
</div>
<script>
const canvas = document.getElementById("canvas");
const gl = canvas.getContext("webgl2", { 
    alpha: false, 
    antialias: false, 
    powerPreference: "high-performance",
    desynchronized: true
});

if (!gl) {
    alert("WebGL 2 not supported!");
    throw new Error("WebGL 2 not supported");
}

canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

// Shaders with texture support and squishing
const vertexShaderSource = `#version 300 es
    in vec2 a_position;
    in vec3 a_instance;
    in vec3 a_color;

    uniform vec2 u_resolution;
    uniform float u_squish;

    out vec3 v_color;
    out vec2 v_texCoord;

    void main() {
        // Apply squish effect to make balls wider
        vec2 squished = a_position;
        squished.x *= u_squish;

        vec2 position = a_instance.xy + squished * a_instance.z;
        vec2 clipSpace = (position / u_resolution) * 2.0 - 1.0;
        gl_Position = vec4(clipSpace * vec2(1, -1), 0, 1);
        v_texCoord = a_position * 0.5 + 0.5;
        v_color = a_color;
    }
`;

const fragmentShaderSource = `#version 300 es
    precision mediump float;

    in vec3 v_color;
    in vec2 v_texCoord;

    uniform sampler2D u_texture;
    uniform int u_textureMode;

    out vec4 fragColor;

    void main() {
        vec2 centered = v_texCoord * 2.0 - 1.0;
        float dist = length(centered);
        if (dist > 1.0) discard;

        if (u_textureMode > 0) {
            vec4 texColor = texture(u_texture, v_texCoord);
            fragColor = texColor;
        } else {
            fragColor = vec4(v_color, 1.0);
        }
    }
`;

function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('Shader error:', gl.getShaderInfoLog(shader));
        return null;
    }
    return shader;
}

function createProgram(gl, vs, fs) {
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error('Program error:', gl.getProgramInfoLog(program));
        return null;
    }
    return program;
}

const vs = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
const fs = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);
const program = createProgram(gl, vs, fs);

const positionLoc = gl.getAttribLocation(program, "a_position");
const instanceLoc = gl.getAttribLocation(program, "a_instance");
const colorLoc = gl.getAttribLocation(program, "a_color");
const resolutionLoc = gl.getUniformLocation(program, "u_resolution");
const textureLoc = gl.getUniformLocation(program, "u_texture");
const textureModeL = gl.getUniformLocation(program, "u_textureMode");
const squishLoc = gl.getUniformLocation(program, "u_squish");

const vao = gl.createVertexArray();
gl.bindVertexArray(vao);

const quadPositions = new Float32Array([
    -1, -1,  1, -1,  -1, 1,
    -1, 1,   1, -1,   1, 1,
]);

const positionBuffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
gl.bufferData(gl.ARRAY_BUFFER, quadPositions, gl.STATIC_DRAW);
gl.enableVertexAttribArray(positionLoc);
gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

const MAX_BALLS = 200000;
const instanceBuffer = gl.createBuffer();
const colorBuffer = gl.createBuffer();

gl.bindBuffer(gl.ARRAY_BUFFER, instanceBuffer);
gl.bufferData(gl.ARRAY_BUFFER, MAX_BALLS * 3 * 4, gl.DYNAMIC_DRAW);
gl.enableVertexAttribArray(instanceLoc);
gl.vertexAttribPointer(instanceLoc, 3, gl.FLOAT, false, 0, 0);
gl.vertexAttribDivisor(instanceLoc, 1);

gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer);
gl.bufferData(gl.ARRAY_BUFFER, MAX_BALLS * 3 * 4, gl.DYNAMIC_DRAW);
gl.enableVertexAttribArray(colorLoc);
gl.vertexAttribPointer(colorLoc, 3, gl.FLOAT, false, 0, 0);
gl.vertexAttribDivisor(colorLoc, 1);

gl.bindVertexArray(null);

gl.useProgram(program);
gl.uniform2f(resolutionLoc, canvas.width, canvas.height);
gl.viewport(0, 0, canvas.width, canvas.height);

// President textures
let obamaTexture = null;
let trumpTexture = null;
let presidentMode = 0; // 0 = normal, 1 = Obama, 2 = Trump
let texturesLoaded = {obama: false, trump: false};

function loadPresidentTextures() {
    // Load Obama
    const obamaImg = new Image();
    obamaImg.crossOrigin = "anonymous";
    obamaImg.onload = () => {
        obamaTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, obamaTexture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, obamaImg);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        texturesLoaded.obama = true;
        console.log('Obama loaded! 🇺🇸');
    };
    obamaImg.src = 'https://upload.wikimedia.org/wikipedia/commons/8/8d/President_Barack_Obama.jpg';

    // Load Trump
    const trumpImg = new Image();
    trumpImg.crossOrigin = "anonymous";
    trumpImg.onload = () => {
        trumpTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, trumpTexture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, trumpImg);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        texturesLoaded.trump = true;
        console.log('Trump loaded! HUGE! 🔶');
    };
    trumpImg.src = 'https://upload.wikimedia.org/wikipedia/commons/5/56/Donald_Trump_official_portrait.jpg';
}

loadPresidentTextures();

// Unified keyboard handler
function handleKeyPress(e) {
    const key = e.key || e;

    if (key === 'g' || key === 'G') {
        gravityWell.active = !gravityWell.active;
        console.log('Gravity:', gravityWell.active ? 'ON' : 'OFF');
    }
    if (key === 't' || key === 'T') {
        presidentMode = presidentMode === 2 ? 0 : 2;
        console.log('Trump mode:', presidentMode === 2 ? 'TREMENDOUS! 🔶' : 'OFF');
    }
    if (key === 'o' || key === 'O') {
        presidentMode = presidentMode === 1 ? 0 : 1;
        console.log('Obama mode:', presidentMode === 1 ? 'YES WE CAN! 🇺🇸' : 'OFF');
    }
    if (key === 'm' || key === 'M') {
        audioMuted = !audioMuted;
        if (!audioMuted && !audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        console.log('Audio:', audioMuted ? 'MUTED' : 'ON');
    }
    if (key === 'r' || key === 'R') {
        ballCount = 0;
        for (let i = 0; i < 10; i++) spawnBall();
        console.log('Reset to 10 balls');
    }
    if (key === ' ') {
        for (let i = 0; i < 100; i++) spawnBall();
        console.log('Spawned 100 balls, total:', ballCount);
    }
}

// Desktop keyboard
document.addEventListener('keydown', handleKeyPress);

// Mobile: Make control buttons clickable
document.querySelectorAll('.control-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const key = btn.getAttribute('data-key');
        handleKeyPress(key);

        // Visual feedback
        btn.style.color = '#ff0';
        setTimeout(() => {
            btn.style.color = '#fff';
        }, 200);
    });
});

// Audio
let audioCtx = null;
let audioMuted = false;

function playTone(freq, dur=0.05, vol=0.03) {
    if (audioMuted || !audioCtx) return;
    try {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.value = freq;
        gain.gain.value = vol;
        osc.start();
        osc.stop(audioCtx.currentTime + dur);
    } catch(e) {}
}

// ULTRA-OPTIMIZED FLAT ARRAYS
const MAX_TOTAL = 500000;
let ballCount = 0;

const ballX = new Float32Array(MAX_TOTAL);
const ballY = new Float32Array(MAX_TOTAL);
const ballR = new Float32Array(MAX_TOTAL);
const ballVX = new Float32Array(MAX_TOTAL);
const ballVY = new Float32Array(MAX_TOTAL);
const ballHue = new Float32Array(MAX_TOTAL);
const ballCooldown = new Uint16Array(MAX_TOTAL);
const ballSplitGroup = new Int32Array(MAX_TOTAL);
const ballSplitTime = new Uint16Array(MAX_TOTAL);
const ballImmune = new Uint8Array(MAX_TOTAL);
const ballIsMini = new Uint8Array(MAX_TOTAL);

function spawnBall(x, y, r, vx, vy, isMini = false) {
    if (ballCount >= MAX_TOTAL) return;
    if (ballCount < 0) ballCount = 0; // Safety check

    const i = ballCount++;
    ballX[i] = x ?? Math.random() * canvas.width;
    ballY[i] = y ?? Math.random() * canvas.height;
    ballR[i] = r ?? (15 + Math.random() * 20);
    ballVX[i] = vx ?? (Math.random() - 0.5) * 4;
    ballVY[i] = vy ?? (Math.random() - 0.5) * 4;
    ballHue[i] = Math.random() * 360;
    ballCooldown[i] = 0;
    ballSplitGroup[i] = -1;
    ballSplitTime[i] = 0;
    ballImmune[i] = 30;
    ballIsMini[i] = isMini ? 1 : 0;
}

for (let i = 0; i < 10; i++) spawnBall();

function removeBall(i) {
    if (ballCount <= 0 || i < 0 || i >= ballCount) return; // Safety check
    const last = ballCount - 1;
    if (i !== last) {
        ballX[i] = ballX[last];
        ballY[i] = ballY[last];
        ballR[i] = ballR[last];
        ballVX[i] = ballVX[last];
        ballVY[i] = ballVY[last];
        ballHue[i] = ballHue[last];
        ballCooldown[i] = ballCooldown[last];
        ballSplitGroup[i] = ballSplitGroup[last];
        ballSplitTime[i] = ballSplitTime[last];
        ballImmune[i] = ballImmune[last];
        ballIsMini[i] = ballIsMini[last];
    }
    ballCount--;
    if (ballCount < 0) ballCount = 0; // Prevent negative count
}

function hueToRGB(h) {
    h = h / 360;
    const c = 1;
    const x = c * (1 - Math.abs((h * 6) % 2 - 1));

    let r, g, b;
    if (h < 1/6) { r = c; g = x; b = 0; }
    else if (h < 2/6) { r = x; g = c; b = 0; }
    else if (h < 3/6) { r = 0; g = c; b = x; }
    else if (h < 4/6) { r = 0; g = x; b = c; }
    else if (h < 5/6) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }

    return [r, g, b];
}

// Adaptive grid - scales with ball count for performance
let GRID_SIZE = 20;
let cellSize;
let grid = [];

function initGrid() {
    // Adaptive grid size based on ball count for optimal performance
    if (ballCount < 1000) GRID_SIZE = 20;
    else if (ballCount < 10000) GRID_SIZE = 40;
    else if (ballCount < 100000) GRID_SIZE = 80;
    else GRID_SIZE = 160; // For millions of balls

    cellSize = Math.max(canvas.width, canvas.height) / GRID_SIZE;
    grid = [];
    for (let i = 0; i < GRID_SIZE * GRID_SIZE; i++) {
        grid[i] = [];
    }
}

function getCell(x, y) {
    x = Math.max(0, Math.min(canvas.width - 1, x));
    y = Math.max(0, Math.min(canvas.height - 1, y));

    const col = Math.min(GRID_SIZE - 1, Math.floor(x / cellSize));
    const row = Math.min(GRID_SIZE - 1, Math.floor(y / cellSize));

    return row * GRID_SIZE + col;
}

initGrid();

let gravityWell = {x: canvas.width / 2, y: canvas.height / 2, active: false};
let physicsTick = 0;
let splitGroupCounter = 0;

canvas.addEventListener('mousemove', e => {
    if (gravityWell.active) {
        gravityWell.x = e.clientX;
        gravityWell.y = e.clientY;
    }
});

let isDragging = false;
let startX = 0, startY = 0;
let draggedBall = -1;

canvas.addEventListener('mousedown', e => {
    e.preventDefault();
    startX = e.clientX;
    startY = e.clientY;
    isDragging = true;
    draggedBall = -1;

    for (let i = 0; i < ballCount; i++) {
        const dx = ballX[i] - startX, dy = ballY[i] - startY;
        if (dx*dx + dy*dy < ballR[i]*ballR[i]) {
            draggedBall = i;
            ballVX[i] = 0;
            ballVY[i] = 0;
            ballImmune[i] = 30;
            break;
        }
    }
});

canvas.addEventListener('mousemove', e => {
    if (!isDragging) return;
    e.preventDefault();
    if (draggedBall >= 0) {
        ballX[draggedBall] = e.clientX;
        ballY[draggedBall] = e.clientY;
    }
});

canvas.addEventListener('mouseup', e => {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;

    if (draggedBall >= 0) {
        ballVX[draggedBall] = dx / 10;
        ballVY[draggedBall] = dy / 10;
    } else if (dx*dx + dy*dy > 100) {
        spawnBall(startX, startY, 20, dx / 10, dy / 10);
    }

    isDragging = false;
    draggedBall = -1;
});

canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    const t = e.touches[0];
    startX = t.clientX;
    startY = t.clientY;
    isDragging = true;
    draggedBall = -1;

    for (let i = 0; i < ballCount; i++) {
        const dx = ballX[i] - startX, dy = ballY[i] - startY;
        if (dx*dx + dy*dy < ballR[i]*ballR[i]) {
            draggedBall = i;
            ballVX[i] = 0;
            ballVY[i] = 0;
            ballImmune[i] = 30;
            break;
        }
    }
}, {passive: false});

canvas.addEventListener('touchmove', e => {
    if (!isDragging) return;
    e.preventDefault();
    const t = e.touches[0];
    if (draggedBall >= 0) {
        ballX[draggedBall] = t.clientX;
        ballY[draggedBall] = t.clientY;
    }
}, {passive: false});

canvas.addEventListener('touchend', e => {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.changedTouches[0].clientX - startX;
    const dy = e.changedTouches[0].clientY - startY;

    if (draggedBall >= 0) {
        ballVX[draggedBall] = dx / 10;
        ballVY[draggedBall] = dy / 10;
    } else if (dx*dx + dy*dy > 100) {
        spawnBall(startX, startY, 20, dx / 10, dy / 10);
    }

    isDragging = false;
    draggedBall = -1;
}, {passive: false});

function explodeBall(i) {
    playTone(440 + Math.random() * 440);

    const x = ballX[i], y = ballY[i], r = ballR[i];

    // Create more balls on explosion for exponential growth
    for (let j = 0; j < 5; j++) { // Increased from 3 to 5 balls per explosion
        const angle = Math.random() * Math.PI * 2;
        const speed = 10 + Math.random() * 5;
        spawnBall(x, y, r / 3, Math.cos(angle) * speed, Math.sin(angle) * speed, true);
    }
}

// SUPER OPTIMIZED COLLISION - optimized for millions of balls
function handleCollisions() {
    // Recalculate grid size if needed
    if (physicsTick % 60 === 0) {
        initGrid();
    }

    // Clear grid
    for (let i = 0; i < grid.length; i++) grid[i].length = 0;

    // Populate grid
    for (let i = 0; i < ballCount; i++) {
        grid[getCell(ballX[i], ballY[i])].push(i);
    }

    physicsTick++;

    // Gravity - skip more aggressively for large ball counts
    const gravitySkip = ballCount > 100000 ? 32 : (ballCount > 10000 ? 16 : 8);
    if (gravityWell.active && (ballCount < 10000 || physicsTick % gravitySkip === 0)) {
        const gx = gravityWell.x, gy = gravityWell.y;
        const strength = 0.08;
        const maxDistSq = 40000;

        // Process in chunks for large counts
        const chunkSize = ballCount > 100000 ? 10000 : ballCount;
        for (let chunk = 0; chunk < ballCount; chunk += chunkSize) {
            const end = Math.min(chunk + chunkSize, ballCount);
            for (let i = chunk; i < end; i++) {
                if (ballIsMini[i] || ballR[i] < 10) continue;

                const dx = gx - ballX[i], dy = gy - ballY[i];
                const distSq = dx * dx + dy * dy;
                if (distSq > maxDistSq || distSq < 1) continue;

                const accel = strength / distSq;
                const dist = Math.sqrt(distSq);
                ballVX[i] += (dx / dist) * accel;
                ballVY[i] += (dy / dist) * accel;
            }
        }
    }

    // Collision detection - adaptive frequency based on ball count
    const collisionSkip = ballCount > 100000 ? 3 : (ballCount > 10000 ? 2 : 1);
    if (physicsTick % collisionSkip !== 0) return;

    const toRemove = [];
    // Use bit array for processed pairs - much faster than Set for millions
    const pairBits = new Uint8Array(Math.ceil((ballCount * ballCount) / 8));
    const getPairBit = (i, j) => {
        const idx = i < j ? i * ballCount + j : j * ballCount + i;
        return (pairBits[Math.floor(idx / 8)] >> (idx % 8)) & 1;
    };
    const setPairBit = (i, j) => {
        const idx = i < j ? i * ballCount + j : j * ballCount + i;
        pairBits[Math.floor(idx / 8)] |= 1 << (idx % 8);
    };

    // Clear pair bits
    pairBits.fill(0);

    // Process collisions - limit checks for very large counts
    const maxChecks = ballCount > 100000 ? 50000 : (ballCount > 10000 ? 20000 : ballCount);
    let checksDone = 0;

    for (let i = 0; i < ballCount && checksDone < maxChecks; i++) {
        // Skip only very small balls with cooldown (allow most balls to merge)
        if (ballCooldown[i] > 0 && ballR[i] < 3) continue;

        const cellIdx = getCell(ballX[i], ballY[i]);
        const row = Math.floor(cellIdx / GRID_SIZE);
        const col = cellIdx % GRID_SIZE;

        for (let dr = -1; dr <= 1; dr++) {
            for (let dc = -1; dc <= 1; dc++) {
                const nr = row + dr;
                const nc = col + dc;

                if (nr < 0 || nr >= GRID_SIZE || nc < 0 || nc >= GRID_SIZE) continue;

                const checkCell = nr * GRID_SIZE + nc;

                for (const j of grid[checkCell]) {
                    if (j <= i || checksDone >= maxChecks) continue;
                    checksDone++;

                    // Skip only very small balls with cooldown (allow most balls to merge)
                    if (ballCooldown[j] > 0 && ballR[j] < 3) continue;

                    // Avoid processing same pair twice
                    if (getPairBit(i, j)) continue;
                    setPairBit(i, j);

                    // Skip if same split group and recently split
                    if (ballSplitGroup[i] >= 0 && ballSplitGroup[j] === ballSplitGroup[i] && 
                        ballSplitTime[i] < 120 && ballSplitTime[j] < 120) continue;

                    const dx = ballX[j] - ballX[i];
                    const dy = ballY[j] - ballY[i];
                    const distSq = dx * dx + dy * dy;
                    const minDist = ballR[i] + ballR[j];
                    const minDistSq = minDist * minDist;

                    if (distSq < minDistSq && distSq > 0.01) {
                        const dist = Math.sqrt(distSq);
                        const overlap = minDist - dist;

                        // Separate balls to prevent overlap
                        const separationX = (dx / dist) * overlap * 0.5;
                        const separationY = (dy / dist) * overlap * 0.5;
                        ballX[i] -= separationX;
                        ballY[i] -= separationY;
                        ballX[j] += separationX;
                        ballY[j] += separationY;

                        // Check if we should merge (on every collision)
                        const speedA = ballVX[i] * ballVX[i] + ballVY[i] * ballVY[i];
                        const speedB = ballVX[j] * ballVX[j] + ballVY[j] * ballVY[j];

                        // All balls can merge - much more lenient conditions
                        const isMiniA = ballIsMini[i] || ballR[i] < 12;
                        const isMiniB = ballIsMini[j] || ballR[j] < 12;

                        let shouldMerge = false;
                        if (isMiniA || isMiniB) {
                            // Mini balls can merge if speed < 500 (very lenient)
                            shouldMerge = (speedA <= 500 && speedB <= 500);
                        } else {
                            // Regular balls merge if speed < 400 (very lenient)
                            shouldMerge = (speedA <= 400 && speedB <= 400);
                        }

                        if (shouldMerge) {
                            const fast = speedA > speedB ? i : j;
                            ballR[i] += ballR[j];
                            ballVX[i] = ballVX[fast] * 1.03;
                            ballVY[i] = ballVY[fast] * 1.03;
                            ballCooldown[i] = 50; // Reduced cooldown for more merging
                            toRemove.push(j);
                            playTone(220 + Math.random() * 440, 0.05, 0.02);
                            continue;
                        }

                        // Collision response (bounce) - elastic collision with speed increase
                        const nx = dx / dist;
                        const ny = dy / dist;
                        const relativeVx = ballVX[j] - ballVX[i];
                        const relativeVy = ballVY[j] - ballVY[i];
                        const dotProduct = relativeVx * nx + relativeVy * ny;

                        if (dotProduct > 0) continue; // Already separating

                        // Mass based on radius squared (area)
                        const massI = ballR[i] * ballR[i];
                        const massJ = ballR[j] * ballR[j];
                        const totalMass = massI + massJ;

                        // Elastic collision with speed boost (1.05x multiplier)
                        const impulse = (2 * dotProduct) / totalMass;
                        const speedBoost = 1.05; // Balls speed up 5% on each bounce

                        ballVX[i] += impulse * massJ * nx * speedBoost;
                        ballVY[i] += impulse * massJ * ny * speedBoost;
                        ballVX[j] -= impulse * massI * nx * speedBoost;
                        ballVY[j] -= impulse * massI * ny * speedBoost;
                    }
                }
            }
        }
    }

    // Remove duplicates and sort in descending order
    const uniqueRemove = [...new Set(toRemove)].sort((a, b) => b - a);
    for (const idx of uniqueRemove) {
        if (idx >= 0 && idx < ballCount && ballCount > 0) {
            removeBall(idx);
        }
    }

    // Splitting - creates 6 balls at 60° intervals (all balls can split)
    // Skip splitting check for very large counts to save performance
    const splitCheckSkip = ballCount > 100000 ? 10 : (ballCount > 10000 ? 5 : 1);
    if (physicsTick % splitCheckSkip === 0) {
        for (let i = ballCount - 1; i >= 0; i--) {
            if (ballR[i] > 20 && ballCooldown[i] <= 0) { // Lowered threshold so smaller balls can split
            const r = ballR[i] / 3; // Smaller balls
            const baseSpeed = 4.5; // Reduced from 7, with some variation
            const groupId = splitGroupCounter++;
            const offset = r * 1.5;
            const x = ballX[i];
            const y = ballY[i];
            const parentVX = ballVX[i];
            const parentVY = ballVY[i];

            // Create 6 balls at 60° intervals (π/3 radians)
            for (let j = 0; j < 6; j++) {
                const angle = (j * Math.PI / 3) + (Math.random() - 0.5) * 0.2; // 60° intervals with slight randomness
                const speed = baseSpeed + (Math.random() - 0.5) * 1.5; // Speed variation

                spawnBall(
                    Math.max(r, Math.min(canvas.width - r, x + Math.cos(angle) * offset)),
                    Math.max(r, Math.min(canvas.height - r, y + Math.sin(angle) * offset)),
                    r, 
                    Math.cos(angle) * speed + parentVX * 0.3, // Add some parent momentum
                    Math.sin(angle) * speed + parentVY * 0.3
                );
                ballSplitGroup[ballCount - 1] = groupId;
                ballImmune[ballCount - 1] = 30;
            }

            // Remove the original ball
            removeBall(i);
            playTone(150 + Math.random() * 200, 0.1, 0.02);
            }
        }
    }

const renderInstanceData = new Float32Array(MAX_BALLS * 3);
const renderColorData = new Float32Array(MAX_BALLS * 3);

function render() {
    let renderCount = 0;

    // Frustum culling with LOD (Level of Detail) for millions
    const renderStep = ballCount > 100000 ? 2 : (ballCount > 50000 ? 1 : 1);
    const maxRender = ballCount > 100000 ? 200000 : MAX_BALLS;

    for (let i = 0; i < ballCount && renderCount < maxRender; i += renderStep) {
        const x = ballX[i], y = ballY[i], r = ballR[i];
        if (x + r >= 0 && x - r <= canvas.width && y + r >= 0 && y - r <= canvas.height) {
            const color = hueToRGB(ballHue[i]);

            const idx = renderCount * 3;
            renderInstanceData[idx] = x;
            renderInstanceData[idx + 1] = y;
            renderInstanceData[idx + 2] = r;

            renderColorData[idx] = color[0];
            renderColorData[idx + 1] = color[1];
            renderColorData[idx + 2] = color[2];

            renderCount++;
        }
    }

    gl.clearColor(0.067, 0.067, 0.067, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);

    if (renderCount > 0) {
        gl.bindVertexArray(vao);

        // Set texture mode and squish factor
        gl.uniform1i(textureModeL, presidentMode);

        // Obama gets fat (1.4x wider), Trump gets normal
        const squish = presidentMode === 1 ? 1.4 : 1.0;
        gl.uniform1f(squishLoc, squish);

        if (presidentMode === 1 && texturesLoaded.obama) {
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, obamaTexture);
            gl.uniform1i(textureLoc, 0);
        } else if (presidentMode === 2 && texturesLoaded.trump) {
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, trumpTexture);
            gl.uniform1i(textureLoc, 0);
        }

        const BATCH_SIZE = 50000;
        const numBatches = Math.ceil(renderCount / BATCH_SIZE);

        for (let batch = 0; batch < numBatches; batch++) {
            const start = batch * BATCH_SIZE;
            const count = Math.min(BATCH_SIZE, renderCount - start);

            if (count <= 0) break;

            gl.bindBuffer(gl.ARRAY_BUFFER, instanceBuffer);
            gl.bufferSubData(gl.ARRAY_BUFFER, 0, renderInstanceData, start * 3, count * 3);

            gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer);
            gl.bufferSubData(gl.ARRAY_BUFFER, 0, renderColorData, start * 3, count * 3);

            gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, count);
        }

        gl.bindVertexArray(null);
    }
}

let lastTime = performance.now();
let frameCount = 0;
let fpsTime = 0;

function animate(currentTime) {
    requestAnimationFrame(animate);

    const delta = currentTime - lastTime;

    if (delta > 200) {
        lastTime = currentTime;
        return;
    }

    frameCount++;
    fpsTime += delta;

    if (fpsTime >= 1000) {
        document.getElementById('fps').textContent = Math.round(frameCount * 1000 / fpsTime);
        frameCount = 0;
        fpsTime = 0;
    }

    lastTime = currentTime;

    handleCollisions();

    const toExplode = [];
    const w = canvas.width, h = canvas.height;

    // FAST movement loop
    for (let i = 0; i < ballCount; i++) {
        ballX[i] += ballVX[i];
        ballY[i] += ballVY[i];

        let bounced = false;
        let bounceX = false;
        let bounceY = false;

        if (ballX[i] - ballR[i] < 0) { 
            ballX[i] = ballR[i]; 
            ballVX[i] = Math.abs(ballVX[i]) * 1.1; 
            bounced = true;
            bounceX = true;
        }
        if (ballX[i] + ballR[i] > w) { 
            ballX[i] = w - ballR[i]; 
            ballVX[i] = -Math.abs(ballVX[i]) * 1.1; 
            bounced = true;
            bounceX = true;
        }
        if (ballY[i] - ballR[i] < 0) { 
            ballY[i] = ballR[i]; 
            ballVY[i] = Math.abs(ballVY[i]) * 1.1; 
            bounced = true;
            bounceY = true;
        }
        if (ballY[i] + ballR[i] > h) { 
            ballY[i] = h - ballR[i]; 
            ballVY[i] = -Math.abs(ballVY[i]) * 1.1; 
            bounced = true;
            bounceY = true;
        }

        if (bounced) {
            // Add slight randomness to prevent corner-to-corner bouncing
            const randomAngle = (Math.random() - 0.5) * 0.15; // ±4.3 degrees
            const cos = Math.cos(randomAngle);
            const sin = Math.sin(randomAngle);

            // Rotate velocity slightly to break corner-to-corner pattern
            const vx = ballVX[i];
            const vy = ballVY[i];
            ballVX[i] = vx * cos - vy * sin;
            ballVY[i] = vx * sin + vy * cos;

            // Speed boost
            ballVX[i] *= 1.02;
            ballVY[i] *= 1.02;
        }

        // Skip hue update for very large counts (visual only)
        if (ballCount < 100000 || i % 10 === 0) {
            ballHue[i] = (ballHue[i] + 2) % 360;
        }
        if (ballCooldown[i] > 0) ballCooldown[i]--;
        if (ballSplitGroup[i] >= 0) ballSplitTime[i]++;
        if (ballImmune[i] > 0) ballImmune[i]--;

        // All balls can explode (removed mini ball restriction)
        if (ballImmune[i] <= 0) {
            const speedSq = ballVX[i] * ballVX[i] + ballVY[i] * ballVY[i];
            // Cap explosion threshold to prevent too many simultaneous explosions
            if (speedSq > 400 && speedSq < 10000) toExplode.push(i);
        }
    }

    // Sort indices in descending order and remove duplicates
    const uniqueExplode = [...new Set(toExplode)].sort((a, b) => b - a);

    for (let i = 0; i < uniqueExplode.length; i++) {
        const idx = uniqueExplode[i];
        if (idx >= 0 && idx < ballCount && ballCount > 0) {
            explodeBall(idx);
            removeBall(idx);
        }
    }

    document.getElementById('ballCount').textContent = ballCount;

    render();
}

window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(resolutionLoc, canvas.width, canvas.height);
    initGrid();
});

console.log('Ultra-optimized + 6-ball hexagon split! Press O for Obama (thicc), T for Trump! 🇺🇸');
animate(performance.now());
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
