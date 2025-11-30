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
    <div>G: gravity | T: trails | R: reset | M: mute | SPACE: +100 balls</div>
    <div>Balls: <span id="ballCount">10</span> | FPS: <span id="fps">60</span></div>
</div>
<script>
const canvas = document.getElementById("canvas");
const gl = canvas.getContext("webgl2", { 
    alpha: false, 
    antialias: false, 
    powerPreference: "high-performance"
});

if (!gl) {
    alert("WebGL 2 not supported! Please use a modern browser.");
    throw new Error("WebGL 2 not supported");
}

canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

// WebGL 2 instanced rendering shaders
const vertexShaderSource = `#version 300 es
    in vec2 a_position;
    in vec3 a_instance;
    in vec3 a_color;

    uniform vec2 u_resolution;

    out vec3 v_color;
    out vec2 v_texCoord;

    void main() {
        vec2 position = a_instance.xy + a_position * a_instance.z;
        vec2 clipSpace = (position / u_resolution) * 2.0 - 1.0;
        gl_Position = vec4(clipSpace * vec2(1, -1), 0, 1);
        v_texCoord = a_position;
        v_color = a_color;
    }
`;

const fragmentShaderSource = `#version 300 es
    precision mediump float;

    in vec3 v_color;
    in vec2 v_texCoord;

    out vec4 fragColor;

    void main() {
        float dist = length(v_texCoord);
        if (dist > 1.0) discard;
        fragColor = vec4(v_color, 1.0);
    }
`;

function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('Shader compile error:', gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

function createProgram(gl, vertexShader, fragmentShader) {
    const program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error('Program link error:', gl.getProgramInfoLog(program));
        gl.deleteProgram(program);
        return null;
    }
    return program;
}

const vertShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
const fragShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);
const program = createProgram(gl, vertShader, fragShader);

const positionLoc = gl.getAttribLocation(program, "a_position");
const instanceLoc = gl.getAttribLocation(program, "a_instance");
const colorLoc = gl.getAttribLocation(program, "a_color");
const resolutionLoc = gl.getUniformLocation(program, "u_resolution");

// Create VAO
const vao = gl.createVertexArray();
gl.bindVertexArray(vao);

// Quad positions
const quadPositions = new Float32Array([
    -1, -1,  1, -1,  -1, 1,
    -1, 1,   1, -1,   1, 1,
]);

const positionBuffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
gl.bufferData(gl.ARRAY_BUFFER, quadPositions, gl.STATIC_DRAW);
gl.enableVertexAttribArray(positionLoc);
gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

// Instance buffers - larger capacity
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

// Audio
let audioCtx = null;
let audioMuted = false;

function playTone(frequency, duration=0.05, volume=0.03) {
    if (audioMuted || !audioCtx) return;
    try {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.value = frequency;
        gain.gain.value = volume;
        osc.start();
        osc.stop(audioCtx.currentTime + duration);
    } catch(e) {}
}

// Ball class
class Ball {
    constructor(x, y, r, vx = 0, vy = 0) {
        this.x = x;
        this.y = y;
        this.r = r;
        this.vx = vx || (Math.random() - 0.5) * 4;
        this.vy = vy || (Math.random() - 0.5) * 4;
        this.hue = Math.random() * 360;
        this.cooldown = 0;
        this.splitGroup = -1;
        this.splitTime = 0;
        this.immune = 30;
        this.isMini = false;
    }

    move(width, height) {
        this.x += this.vx;
        this.y += this.vy;

        let bounced = false;
        if (this.x - this.r < 0) { 
            this.x = this.r; 
            this.vx = Math.abs(this.vx) * 1.1; 
            bounced = true; 
        }
        if (this.x + this.r > width) { 
            this.x = width - this.r; 
            this.vx = -Math.abs(this.vx) * 1.1; 
            bounced = true; 
        }
        if (this.y - this.r < 0) { 
            this.y = this.r; 
            this.vy = Math.abs(this.vy) * 1.1; 
            bounced = true; 
        }
        if (this.y + this.r > height) { 
            this.y = height - this.r; 
            this.vy = -Math.abs(this.vy) * 1.1; 
            bounced = true; 
        }

        if (bounced) {
            this.vx *= 1.02;
            this.vy *= 1.02;
        }

        this.hue = (this.hue + 2) % 360;
        if (this.cooldown > 0) this.cooldown--;
        if (this.splitGroup >= 0) this.splitTime++;
        if (this.immune > 0) this.immune--;

        if (this.immune <= 0 && !this.isMini) {
            const speedSq = this.vx * this.vx + this.vy * this.vy;
            if (speedSq > 625) return true;
        }
        return false;
    }

    getColor() {
        const h = this.hue / 360;
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
}

// Fixed spatial grid
let GRID_SIZE = 16;
let cellSize;
let grid = [];

function initGrid() {
    cellSize = Math.max(canvas.width, canvas.height) / GRID_SIZE;
    grid = [];
    for (let i = 0; i < GRID_SIZE * GRID_SIZE; i++) {
        grid[i] = [];
    }
}

function updateGridSize(ballCount) {
    const newSize = Math.max(12, Math.min(32, Math.ceil(Math.sqrt(ballCount / 3))));
    if (newSize !== GRID_SIZE) {
        GRID_SIZE = newSize;
        initGrid();
    }
}

function getCell(x, y) {
    // Clamp coordinates to canvas bounds first
    x = Math.max(0, Math.min(canvas.width - 1, x));
    y = Math.max(0, Math.min(canvas.height - 1, y));

    const col = Math.floor(x / cellSize);
    const row = Math.floor(y / cellSize);

    // Extra safety clamp on grid indices
    const clampedCol = Math.max(0, Math.min(GRID_SIZE - 1, col));
    const clampedRow = Math.max(0, Math.min(GRID_SIZE - 1, row));

    return clampedRow * GRID_SIZE + clampedCol;
}

initGrid();

let balls = [];
let splitGroupCounter = 0;

function spawnBall(x, y, r, vx, vy, isMini = false) {
    const b = new Ball(
        x ?? Math.random() * canvas.width,
        y ?? Math.random() * canvas.height,
        r ?? (15 + Math.random() * 20),
        vx, vy
    );
    b.isMini = isMini;
    b.immune = 30;
    balls.push(b);
}

for (let i = 0; i < 10; i++) spawnBall();

// Globals
let gravityWell = {x: canvas.width / 2, y: canvas.height / 2, active: false, strength: 0.08};
let physicsTick = 0;

document.addEventListener('keydown', e => {
    if (e.key === 'g' || e.key === 'G') {
        gravityWell.active = !gravityWell.active;
        console.log('Gravity:', gravityWell.active ? 'ON' : 'OFF');
    }
    if (e.key === 'm' || e.key === 'M') {
        audioMuted = !audioMuted;
        if (!audioMuted && !audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        console.log('Audio:', audioMuted ? 'MUTED' : 'ON');
    }
    if (e.key === 'r' || e.key === 'R') {
        balls = [];
        for (let i = 0; i < 10; i++) spawnBall();
        console.log('Reset to 10 balls');
    }
    if (e.key === ' ') {
        e.preventDefault();
        // Warn if approaching limits
        if (balls.length > 150000) {
            console.warn('⚠️ Approaching device limits! Count:', balls.length);
        }
        for (let i = 0; i < 100; i++) spawnBall();
        console.log('Spawned 100 balls, total:', balls.length);
    }
});

canvas.addEventListener('mousemove', e => {
    if (gravityWell.active) {
        gravityWell.x = e.clientX;
        gravityWell.y = e.clientY;
    }
});

// Drag handling
let isDragging = false;
let startX = 0, startY = 0;
let draggedBall = null;

canvas.addEventListener('mousedown', e => {
    e.preventDefault();
    startX = e.clientX;
    startY = e.clientY;
    isDragging = true;
    draggedBall = null;

    for (let b of balls) {
        const dx = b.x - startX, dy = b.y - startY;
        if (dx*dx + dy*dy < b.r*b.r) {
            draggedBall = b;
            b.vx = 0; b.vy = 0; b.immune = 30;
            break;
        }
    }
});

canvas.addEventListener('mousemove', e => {
    if (!isDragging) return;
    e.preventDefault();
    if (draggedBall) {
        draggedBall.x = e.clientX;
        draggedBall.y = e.clientY;
    }
});

canvas.addEventListener('mouseup', e => {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;

    if (draggedBall) {
        draggedBall.vx = dx / 10;
        draggedBall.vy = dy / 10;
    } else if (dx*dx + dy*dy > 100) {
        spawnBall(startX, startY, 20, dx / 10, dy / 10);
    }

    isDragging = false;
    draggedBall = null;
});

// Touch
canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    const t = e.touches[0];
    startX = t.clientX;
    startY = t.clientY;
    isDragging = true;
    draggedBall = null;

    for (let b of balls) {
        const dx = b.x - startX, dy = b.y - startY;
        if (dx*dx + dy*dy < b.r*b.r) {
            draggedBall = b;
            b.vx = 0; b.vy = 0; b.immune = 30;
            break;
        }
    }
}, {passive: false});

canvas.addEventListener('touchmove', e => {
    if (!isDragging) return;
    e.preventDefault();
    const t = e.touches[0];
    if (draggedBall) {
        draggedBall.x = t.clientX;
        draggedBall.y = t.clientY;
    }
}, {passive: false});

canvas.addEventListener('touchend', e => {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.changedTouches[0].clientX - startX;
    const dy = e.changedTouches[0].clientY - startY;

    if (draggedBall) {
        draggedBall.vx = dx / 10;
        draggedBall.vy = dy / 10;
    } else if (dx*dx + dy*dy > 100) {
        spawnBall(startX, startY, 20, dx / 10, dy / 10);
    }

    isDragging = false;
    draggedBall = null;
}, {passive: false});

function explodeBall(ball) {
    playTone(440 + Math.random() * 440);

    for (let i = 0; i < 3; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 10 + Math.random() * 5;
        spawnBall(ball.x, ball.y, ball.r / 3, 
            Math.cos(angle) * speed, 
            Math.sin(angle) * speed, true);
    }
}

// Optimized collision handling
function handleCollisions() {
    const len = balls.length;
    updateGridSize(len);

    // Clear grid safely
    for (let i = 0; i < grid.length; i++) {
        grid[i].length = 0;
    }

    // Populate grid with bounds checking
    for (let i = 0; i < len; i++) {
        const b = balls[i];
        const cellIdx = getCell(b.x, b.y);
        if (cellIdx >= 0 && cellIdx < grid.length) {
            grid[cellIdx].push(i);
        }
    }

    physicsTick++;

    // At very high counts, reduce physics frequency more aggressively
    const doExpensivePhysics = len < 5000 || (len < 50000 && physicsTick % 5 === 0) || physicsTick % 10 === 0;

    // Gravity well
    if (doExpensivePhysics && gravityWell.active) {
        const gx = gravityWell.x, gy = gravityWell.y;
        const strength = gravityWell.strength;

        for (let i = 0; i < len; i++) {
            const b = balls[i];
            if (b.isMini || b.r < 10) continue;

            const dx = gx - b.x, dy = gy - b.y;
            const distSq = dx * dx + dy * dy;
            if (distSq > 40000 || distSq < 1) continue;

            const accel = strength / distSq;
            const dist = Math.sqrt(distSq);
            b.vx += (dx / dist) * accel;
            b.vy += (dy / dist) * accel;
        }
    }

    // Merging - reduce frequency at extreme counts
    const mergingInterval = len < 50000 ? 3 : 10;
    if (physicsTick % mergingInterval === 0) {
        const toRemove = new Set();

        for (let i = 0; i < len; i++) {
            if (toRemove.has(i)) continue;

            const a = balls[i];
            if (a.cooldown > 0 || a.r < 5) continue;

            const cellIdx = getCell(a.x, a.y);
            const row = Math.floor(cellIdx / GRID_SIZE);
            const col = cellIdx % GRID_SIZE;

            for (let dr = -1; dr <= 1; dr++) {
                for (let dc = -1; dc <= 1; dc++) {
                    const nr = row + dr;
                    const nc = col + dc;

                    if (nr < 0 || nr >= GRID_SIZE || nc < 0 || nc >= GRID_SIZE) continue;

                    const checkCell = nr * GRID_SIZE + nc;

                    for (const j of grid[checkCell]) {
                        if (j <= i || toRemove.has(j)) continue;

                        const b = balls[j];
                        if (b.cooldown > 0 || b.r < 5) continue;
                        if (a.splitGroup >= 0 && b.splitGroup === a.splitGroup && 
                            a.splitTime < 120 && b.splitTime < 120) continue;

                        const dx = b.x - a.x, dy = b.y - a.y;
                        const minDist = a.r + b.r;
                        const distSq = dx * dx + dy * dy;

                        if (distSq < minDist * minDist) {
                            const speedA = a.vx * a.vx + a.vy * a.vy;
                            const speedB = b.vx * b.vx + b.vy * b.vy;
                            const fast = speedA > speedB ? a : b;

                            a.r += b.r;
                            a.vx = fast.vx * 1.03;
                            a.vy = fast.vy * 1.03;
                            a.cooldown = 100;

                            toRemove.add(j);
                            playTone(220 + Math.random() * 440, 0.05, 0.02);
                            break;
                        }
                    }
                }
            }
        }

        // Remove merged balls
        if (toRemove.size > 0) {
            const removeArray = Array.from(toRemove).sort((a, b) => b - a);
            for (const idx of removeArray) {
                balls[idx] = balls[balls.length - 1];
                balls.pop();
            }
        }
    }

    // Split large balls
    const newBalls = [];
    for (let i = balls.length - 1; i >= 0; i--) {
        const b = balls[i];
        if (b.r > 50 && b.cooldown <= 0) {
            const r = b.r / 2;
            b.r = r;
            b.cooldown = 100;

            const angle = Math.random() * Math.PI * 2;
            const speed = 7;
            const groupId = splitGroupCounter++;
            const offset = r * 1.2;

            const b1 = new Ball(
                Math.max(r, Math.min(canvas.width - r, b.x + Math.cos(angle) * offset)),
                Math.max(r, Math.min(canvas.height - r, b.y + Math.sin(angle) * offset)),
                r,
                Math.cos(angle) * speed,
                Math.sin(angle) * speed
            );
            b1.splitGroup = groupId;
            b1.splitTime = 0;
            b1.immune = 30;

            const b2 = new Ball(
                Math.max(r, Math.min(canvas.width - r, b.x - Math.cos(angle) * offset)),
                Math.max(r, Math.min(canvas.height - r, b.y - Math.sin(angle) * offset)),
                r,
                -Math.cos(angle) * speed,
                -Math.sin(angle) * speed
            );
            b2.splitGroup = groupId;
            b2.splitTime = 0;
            b2.immune = 30;

            newBalls.push(b1, b2);
            playTone(150 + Math.random() * 200, 0.1, 0.02);
        }
    }

    if (newBalls.length > 0) {
        balls.push(...newBalls);
    }

    // No culling - let it grow!
}

// Instanced rendering
const instanceData = new Float32Array(MAX_BALLS * 3);
const colorData = new Float32Array(MAX_BALLS * 3);

function render() {
    const totalBalls = balls.length;

    // First pass: collect only visible balls
    const visibleBalls = [];
    for (let i = 0; i < totalBalls; i++) {
        const b = balls[i];
        // Check if ball is on screen (with small margin)
        if (b.x + b.r >= 0 && b.x - b.r <= canvas.width &&
            b.y + b.r >= 0 && b.y - b.r <= canvas.height) {
            visibleBalls.push(b);
        }
    }

    const len = Math.min(visibleBalls.length, MAX_BALLS);

    // Fill buffers with only visible balls
    for (let i = 0; i < len; i++) {
        const b = visibleBalls[i];
        const color = b.getColor();

        const i3 = i * 3;
        instanceData[i3] = b.x;
        instanceData[i3 + 1] = b.y;
        instanceData[i3 + 2] = b.r;

        colorData[i3] = color[0];
        colorData[i3 + 1] = color[1];
        colorData[i3 + 2] = color[2];
    }

    try {
        gl.clearColor(0.067, 0.067, 0.067, 1);
        gl.clear(gl.COLOR_BUFFER_BIT);

        gl.bindVertexArray(vao);

        // Batch rendering to avoid iOS WebGL limits
        const BATCH_SIZE = 50000;
        const numBatches = Math.ceil(len / BATCH_SIZE);

        for (let batch = 0; batch < numBatches; batch++) {
            const start = batch * BATCH_SIZE;
            const count = Math.min(BATCH_SIZE, len - start);

            if (count <= 0) break;

            gl.bindBuffer(gl.ARRAY_BUFFER, instanceBuffer);
            gl.bufferSubData(gl.ARRAY_BUFFER, 0, instanceData, start * 3, count * 3);

            gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer);
            gl.bufferSubData(gl.ARRAY_BUFFER, 0, colorData, start * 3, count * 3);

            gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, count);
        }

        gl.bindVertexArray(null);

        const error = gl.getError();
        if (error !== gl.NO_ERROR) {
            console.error('WebGL Error:', error, 'rendering', len, 'of', totalBalls, 'balls');
        }
    } catch(e) {
        console.error('Render error:', e, 'at', totalBalls, 'balls');
    }
}

// Game loop
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

    // Physics
    handleCollisions();

    // Handle exploding EVERY frame and update count immediately
    const toExplode = [];
    for (let i = 0; i < balls.length; i++) {
        if (balls[i].move(canvas.width, canvas.height)) {
            toExplode.push(i);
        }
    }

    // Explode balls and update count right away
    for (let i = toExplode.length - 1; i >= 0; i--) {
        explodeBall(balls[toExplode[i]]);
        balls.splice(toExplode[i], 1);
    }

    // Update ball count immediately after explosions
    document.getElementById('ballCount').textContent = balls.length;

    render();
}

window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(resolutionLoc, canvas.width, canvas.height);
    initGrid();
});

console.log('WebGL 2 Ready - Press SPACE for +100 balls!');
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