from flask import Flask, render_template_string
import os

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Balls Animation (WEBGL Physics simulator</title>
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
    <div>G: gravity | T: trails | R: reset | M: mute</div>
    <div>Balls: <span id="ballCount">10</span> | FPS: <span id="fps">60</span></div>
</div>
<script>
const canvas = document.getElementById("canvas");
const gl = canvas.getContext("webgl", { alpha: true, antialias: true, preserveDrawingBuffer: false });
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

if (!gl) {
    alert("WebGL not supported!");
    throw new Error("WebGL not supported");
}

// Simple vertex shader for circles
const vertexShaderSource = `
    attribute vec2 a_position;
    uniform vec2 u_resolution;
    uniform vec2 u_center;
    uniform float u_radius;
    varying vec2 v_texCoord;

    void main() {
        vec2 position = u_center + a_position * u_radius;
        vec2 clipSpace = (position / u_resolution) * 2.0 - 1.0;
        gl_Position = vec4(clipSpace * vec2(1, -1), 0, 1);
        v_texCoord = a_position;
    }
`;

// Fragment shader for circles
const fragmentShaderSource = `
    precision mediump float;
    uniform vec3 u_color;
    varying vec2 v_texCoord;

    void main() {
        float dist = length(v_texCoord);
        if (dist > 1.0) {
            discard;
        }
        float alpha = smoothstep(1.0, 0.9, dist);
        gl_FragColor = vec4(u_color, alpha);
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

// Create program
const vertShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
const fragShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);
const program = createProgram(gl, vertShader, fragShader);

if (!program) {
    alert("Failed to create WebGL program!");
    throw new Error("Program creation failed");
}

// Get locations
const positionLoc = gl.getAttribLocation(program, "a_position");
const resolutionLoc = gl.getUniformLocation(program, "u_resolution");
const centerLoc = gl.getUniformLocation(program, "u_center");
const radiusLoc = gl.getUniformLocation(program, "u_radius");
const colorLoc = gl.getUniformLocation(program, "u_color");

// Create quad buffer
const quadPositions = new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
    -1,  1,
     1, -1,
     1,  1,
]);

const positionBuffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
gl.bufferData(gl.ARRAY_BUFFER, quadPositions, gl.STATIC_DRAW);

// Setup WebGL state
gl.enable(gl.BLEND);
gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
gl.viewport(0, 0, canvas.width, canvas.height);

// Use program and setup position attribute
gl.useProgram(program);
gl.enableVertexAttribArray(positionLoc);
gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);
gl.uniform2f(resolutionLoc, canvas.width, canvas.height);

// Audio setup
let audioCtx = null;
let osc = null;
let gainNode = null;
let audioMuted = false;

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        osc = audioCtx.createOscillator();
        gainNode = audioCtx.createGain();
        osc.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        osc.start();
        osc.type = 'sine';
    }
}

function playTone(frequency, duration=0.1, type='sine', volume=0.1) {
    if (audioMuted) return;
    try {
        initAudio();
        osc.type = type;
        osc.frequency.setValueAtTime(frequency, audioCtx.currentTime);
        gainNode.gain.setValueAtTime(volume, audioCtx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + duration);
    } catch(e) {}
}

// Ball class
class Ball {
    constructor(x, y, r) {
        this.x = x;
        this.y = y;
        this.r = r;
        this.vx = (Math.random() - 0.5) * 4;
        this.vy = (Math.random() - 0.5) * 4;
        this.mergeCooldown = 0;
        this.splitTime = 0;
        this.justSplitGroup = null;
        this.explodeImmune = 30;
        this.isMini = false;
        this.hue = Math.random() * 360;

        this.trailHead = 0;
        this.trail = new Array(10).fill(0).map(() => ({x: 0, y: 0}));
        this.trail[0] = {x, y};
    }

    move() {
        this.x += this.vx;
        this.y += this.vy;

        let bounced = false;
        if (this.x - this.r < 0) { this.x = this.r; this.vx = Math.abs(this.vx) * 1.2; bounced = true; }
        if (this.x + this.r > canvas.width) { this.x = canvas.width - this.r; this.vx = -Math.abs(this.vx) * 1.2; bounced = true; }
        if (this.y - this.r < 0) { this.y = this.r; this.vy = Math.abs(this.vy) * 1.2; bounced = true; }
        if (this.y + this.r > canvas.height) { this.y = canvas.height - this.r; this.vy = -Math.abs(this.vy) * 1.2; bounced = true; }

        if (bounced) {
            this.vx *= 0.7;
            this.vy *= 0.7;
        }

        let speed = Math.sqrt(this.vx * this.vx + this.vy * this.vy);
        this.hue = (this.hue + 3) % 360;

        if (this.mergeCooldown > 0) this.mergeCooldown--;
        if (this.justSplitGroup !== null) this.splitTime++;
        if (this.explodeImmune > 0) this.explodeImmune--;

        this.trailHead = (this.trailHead + 1) % 10;
        this.trail[this.trailHead] = {x: this.x, y: this.y};

        if (this.explodeImmune <= 0 && speed > 25 && !this.isMini) {
            explodeBall(this);
        }
    }

    getColor() {
        const h = this.hue / 360;
        const s = 1;
        const l = 0.6;

        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs((h * 6) % 2 - 1));
        const m = l - c / 2;

        let r, g, b;
        if (h < 1/6) { r = c; g = x; b = 0; }
        else if (h < 2/6) { r = x; g = c; b = 0; }
        else if (h < 3/6) { r = 0; g = c; b = x; }
        else if (h < 4/6) { r = 0; g = x; b = c; }
        else if (h < 5/6) { r = x; g = 0; b = c; }
        else { r = c; g = 0; b = x; }

        return [(r + m), (g + m), (b + m)];
    }
}

// Grid for spatial partitioning
let GRID_SIZE = 12;
let cellSize = Math.max(canvas.width, canvas.height) / GRID_SIZE;
let grid = Array(GRID_SIZE * GRID_SIZE).fill().map(() => []);

function updateGrid() {
    const target = Math.max(8, Math.min(24, Math.ceil(Math.sqrt(balls.length))));
    if (target !== GRID_SIZE) {
        GRID_SIZE = target;
        cellSize = Math.max(canvas.width, canvas.height) / GRID_SIZE;
        grid = Array(GRID_SIZE * GRID_SIZE).fill().map(() => []);
    }
}

function mod(n, m) {
    return ((n % m) + m) % m;
}

function getCell(x, y) {
    const col = Math.floor(mod(x / cellSize, GRID_SIZE));
    const row = Math.floor(mod(y / cellSize, GRID_SIZE));
    return row * GRID_SIZE + col;
}

let balls = [];

function spawnBall(x, y, r = null, vx = 0, vy = 0, isMini = false) {
    let b = new Ball(
        x || Math.random() * canvas.width,
        y || Math.random() * canvas.height,
        r || 15 + Math.random() * 20
    );
    b.vx = vx;
    b.vy = vy;
    b.isMini = isMini;
    b.explodeImmune = 30;
    balls.push(b);
}

for (let i = 0; i < 10; i++) spawnBall();

// Globals
let gravityWell = {x: canvas.width / 2, y: canvas.height / 2, active: false, strength: 0.1};
let trailsEnabled = true;
let physicsTick = 0;

document.addEventListener('keydown', e => {
    if (e.key === 'g' || e.key === 'G') {
        gravityWell.active = !gravityWell.active;
        console.log('Gravity well:', gravityWell.active ? 'ON' : 'OFF');
    }
    if (e.key === 't' || e.key === 'T') {
        trailsEnabled = !trailsEnabled;
        console.log('Trails:', trailsEnabled ? 'ON' : 'OFF');
    }
    if (e.key === 'm' || e.key === 'M') {
        audioMuted = !audioMuted;
        console.log('Audio:', audioMuted ? 'MUTED' : 'ON');
    }
    if (e.key === 'r' || e.key === 'R') {
        // Reset all balls and trails
        balls = [];
        for (let i = 0; i < 10; i++) spawnBall();

        // Clear the trails canvas
        trailCtx.fillStyle = '#111';
        trailCtx.fillRect(0, 0, trailCanvas.width, trailCanvas.height);
        console.log('Reset to 10 balls');
    }
    // Spawn 10 more balls with SPACE
    if (e.key === ' ') {
        e.preventDefault();
        for (let i = 0; i < 10; i++) {
            spawnBall(Math.random() * canvas.width, Math.random() * canvas.height);
        }
        console.log('Spawned 10 more balls');
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
let currentX = 0, currentY = 0;
let draggedBall = null;

canvas.addEventListener('mousedown', e => {
    e.preventDefault();
    startX = currentX = e.clientX;
    startY = currentY = e.clientY;
    isDragging = true;
    draggedBall = null;

    for (let b of balls) {
        let dx = b.x - currentX, dy = b.y - currentY;
        if (Math.sqrt(dx * dx + dy * dy) < b.r) {
            draggedBall = b;
            b.vx = 0;
            b.vy = 0;
            b.explodeImmune = 30;
            break;
        }
    }
});

canvas.addEventListener('mousemove', e => {
    if (!isDragging) return;
    e.preventDefault();
    currentX = e.clientX;
    currentY = e.clientY;
    if (draggedBall) {
        draggedBall.x = currentX;
        draggedBall.y = currentY;
        draggedBall.vx = 0;
        draggedBall.vy = 0;
    }
});

canvas.addEventListener('mouseup', e => {
    if (!isDragging) return;
    e.preventDefault();
    let endX = currentX;
    let endY = currentY;
    let dx = endX - startX;
    let dy = endY - startY;
    let dist = Math.sqrt(dx * dx + dy * dy);

    if (draggedBall) {
        draggedBall.vx = dx / 10;
        draggedBall.vy = dy / 10;
    } else if (dist > 10) {
        spawnBall(startX, startY, 20, dx / 10, dy / 10);
    }

    isDragging = false;
    draggedBall = null;
});

// Touch events
canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    let t = e.touches[0];
    startX = currentX = t.clientX;
    startY = currentY = t.clientY;
    isDragging = true;
    draggedBall = null;

    for (let b of balls) {
        let dx = b.x - currentX, dy = b.y - currentY;
        if (Math.sqrt(dx * dx + dy * dy) < b.r) {
            draggedBall = b;
            b.vx = 0;
            b.vy = 0;
            b.explodeImmune = 30;
            break;
        }
    }
}, {passive: false});

canvas.addEventListener('touchmove', e => {
    if (!isDragging) return;
    e.preventDefault();
    let t = e.touches[0];
    currentX = t.clientX;
    currentY = t.clientY;
    if (draggedBall) {
        draggedBall.x = currentX;
        draggedBall.y = currentY;
        draggedBall.vx = 0;
        draggedBall.vy = 0;
    }
}, {passive: false});

canvas.addEventListener('touchend', e => {
    if (!isDragging) return;
    e.preventDefault();
    let endX = currentX;
    let endY = currentY;
    let dx = endX - startX;
    let dy = endY - startY;
    let dist = Math.sqrt(dx * dx + dy * dy);

    if (draggedBall) {
        draggedBall.vx = dx / 10;
        draggedBall.vy = dy / 10;
    } else if (dist > 10) {
        spawnBall(startX, startY, 20, dx / 10, dy / 10);
    }

    isDragging = false;
    draggedBall = null;
}, {passive: false});

let splitGroupCounter = 0;

function handleCollisions() {
    updateGrid();
    grid.forEach(cell => cell.length = 0);
    for (let b of balls) {
        grid[getCell(b.x, b.y)].push(b);
    }

    const doOrbitsGravity = balls.length < 200 || physicsTick % 2 === 0;
    physicsTick++;

    if (doOrbitsGravity) {
        // Orbits
        const orbitFactor = 0.04;
        for (let i = 0; i < balls.length; i++) {
            let a = balls[i];
            if (a.r < 10 || a.isMini) continue;

            const aCell = getCell(a.x, a.y);
            const checkCells = [];
            for (let dx = -1; dx <= 1; dx++) {
                for (let dy = -1; dy <= 1; dy++) {
                    let adj = (aCell + dx + dy * GRID_SIZE + GRID_SIZE * GRID_SIZE) % (GRID_SIZE * GRID_SIZE);
                    checkCells.push(adj);
                }
            }

            for (let cell of checkCells) {
                for (let other of grid[cell]) {
                    if (other === a || other.r < 10 || other.isMini) continue;
                    if (a.justSplitGroup !== null && other.justSplitGroup === a.justSplitGroup && a.splitTime < 120) continue;

                    let dx = other.x - a.x, dy = other.y - a.y;
                    let distSq = dx * dx + dy * dy;
                    if (distSq > 14400 || distSq === 0) continue;

                    let dist = Math.sqrt(distSq);
                    let forceX = -dy / dist * orbitFactor;
                    let forceY = dx / dist * orbitFactor;

                    a.vx += forceX;
                    a.vy += forceY;
                    other.vx -= forceX * 0.5;
                    other.vy -= forceY * 0.5;
                }
            }
        }

        // Gravity
        if (gravityWell.active) {
            const gStrengthBase = gravityWell.strength;
            for (let b of balls) {
                if (b.isMini || b.r < 10) continue;
                let dx = gravityWell.x - b.x, dy = gravityWell.y - b.y;
                let distSq = dx * dx + dy * dy;
                if (distSq > 40000 || distSq === 0) continue;

                let dist = Math.sqrt(distSq);
                let accel = gStrengthBase / distSq;
                b.vx += (dx / dist) * accel;
                b.vy += (dy / dist) * accel;
            }
        }
    }

    // Merges
    for (let i = balls.length - 1; i >= 0; i--) {
        let a = balls[i];
        if (a.mergeCooldown > 0 || a.r < 5) continue;

        const aCell = getCell(a.x, a.y);
        const checkCells = [];
        for (let dx = -1; dx <= 1; dx++) {
            for (let dy = -1; dy <= 1; dy++) {
                let adj = (aCell + dx + dy * GRID_SIZE + GRID_SIZE * GRID_SIZE) % (GRID_SIZE * GRID_SIZE);
                checkCells.push(adj);
            }
        }

        let merged = false;
        for (let cell of checkCells) {
            for (let j = grid[cell].length - 1; j >= 0; j--) {
                let b = grid[cell][j];
                if (b === a || b.mergeCooldown > 0 || b.r < 5) continue;
                if (a.justSplitGroup !== null && b.justSplitGroup === a.justSplitGroup && a.splitTime < 120 && b.splitTime < 120) continue;

                let dx = b.x - a.x, dy = b.y - a.y;
                let distSq = dx * dx + dy * dy;
                if (distSq >= (a.r + b.r) ** 2) continue;

                let dist = Math.sqrt(distSq);
                if (dist < a.r + b.r) {
                    let speedA = a.vx * a.vx + a.vy * a.vy;
                    let speedB = b.vx * b.vx + b.vy * b.vy;
                    let fastBall = speedA > speedB ? a : b;

                    a.r += b.r;
                    a.vx = fastBall.vx * 1.04;
                    a.vy = fastBall.vy * 1.04;
                    a.mergeCooldown = 120;

                    playTone(220 + Math.random() * 440, 0.1, 'square', 0.05);

                    const bGlobalIdx = balls.indexOf(b);
                    if (bGlobalIdx > -1) {
                        balls[bGlobalIdx] = balls[balls.length - 1];
                        balls.pop();
                        if (bGlobalIdx < i) i--;
                    }
                    merged = true;
                    break;
                }
            }
            if (merged) break;
        }
    }

    // Splits
    let newBalls = [];
    for (let i = balls.length - 1; i >= 0; i--) {
        let b = balls[i];
        if (b.r > 50 && b.mergeCooldown <= 0) {
            let r = b.r / 2;
            b.r = r;
            b.mergeCooldown = 120;

            let angle = Math.random() * Math.PI * 2;
            let speed = 8;
            let vx1 = Math.cos(angle) * speed;
            let vy1 = Math.sin(angle) * speed;
            let vx2 = -vx1;
            let vy2 = -vy1;

            splitGroupCounter++;
            let groupId = splitGroupCounter;
            let offDist = r * 1.5;

            let b1x = Math.max(r, Math.min(canvas.width - r, b.x + vx1 / speed * offDist));
            let b1y = Math.max(r, Math.min(canvas.height - r, b.y + vy1 / speed * offDist));
            let b2x = Math.max(r, Math.min(canvas.width - r, b.x + vx2 / speed * offDist));
            let b2y = Math.max(r, Math.min(canvas.height - r, b.y + vy2 / speed * offDist));

            let b1 = new Ball(b1x, b1y, r);
            b1.vx = vx1; b1.vy = vy1; b1.justSplitGroup = groupId; b1.splitTime = 0; b1.explodeImmune = 30;

            let b2 = new Ball(b2x, b2y, r);
            b2.vx = vx2; b2.vy = vy2; b2.justSplitGroup = groupId; b2.splitTime = 0; b2.explodeImmune = 30;

            newBalls.push(b1, b2);
            playTone(110 + Math.random() * 220, 0.15, 'sawtooth', 0.03);
        }
    }
    balls.push(...newBalls);

    // Cull - keep ball count manageable
    if (balls.length > 30000) {
        // Keep only the 3000 fastest balls (they have momentum)
        balls.sort((a, b) => {
            let speedA = Math.sqrt(a.vx * a.vx + a.vy * a.vy);
            let speedB = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
            return speedB - speedA;
        });
        balls.length = 3000;
        console.log('Mass cull: reduced to 3000 fastest balls');
    } else if (balls.length > 50) {
        let cullCount = Math.min(5, balls.length - 40);
        for (let i = 0; i < cullCount; i++) {
            let idx = Math.floor(Math.random() * balls.length);
            explodeBall(balls[idx]);
        }
    }

    document.getElementById('ballCount').textContent = balls.length;
}

function explodeBall(ball) {
    playTone(440 + Math.random() * 440, 0.2, 'triangle', 0.04);

    let miniCount = 4;
    for (let i = 0; i < miniCount; i++) {
        let angle = Math.random() * Math.PI * 2;
        let speed = 10 + Math.random() * 6;
        spawnBall(ball.x, ball.y, ball.r / 3, Math.cos(angle) * speed, Math.sin(angle) * speed, true);
    }

    const idx = balls.indexOf(ball);
    if (idx > -1) balls.splice(idx, 1);
}

// Canvas 2D for trails - BELOW the balls
const trailCanvas = document.createElement('canvas');
const trailCtx = trailCanvas.getContext('2d');
trailCanvas.width = canvas.width;
trailCanvas.height = canvas.height;
trailCanvas.style.position = 'absolute';
trailCanvas.style.top = '0';
trailCanvas.style.left = '0';
trailCanvas.style.pointerEvents = 'none';
trailCanvas.style.zIndex = '1'; // Trails BEHIND
document.body.appendChild(trailCanvas);

// Position WebGL canvas for balls - ABOVE the trails
canvas.style.position = 'absolute';
canvas.style.top = '0';
canvas.style.left = '0';
canvas.style.zIndex = '5'; // Balls ON TOP

// Render function
function render() {
    // Trails layer (BEHIND) - only fade if trails are enabled
    if (trailsEnabled) {
        trailCtx.fillStyle = 'rgba(17,17,17,0.1)';
        trailCtx.fillRect(0, 0, trailCanvas.width, trailCanvas.height);

        if (balls.length < 25) {
            for (let b of balls) {
                if (b.r <= 15) continue;
                let color = b.getColor();
                trailCtx.strokeStyle = `rgb(${color[0]*255},${color[1]*255},${color[2]*255})`;
                trailCtx.lineWidth = 2;
                trailCtx.beginPath();
                let head = b.trailHead;
                for (let i = 0; i < 9; i++) {
                    let idx1 = (head - i + 10) % 10;
                    let idx2 = (head - i - 1 + 10) % 10;
                    let pos1 = b.trail[idx1];
                    let pos2 = b.trail[idx2];
                    if (i === 0) trailCtx.moveTo(pos1.x, pos1.y);
                    trailCtx.lineTo(pos2.x, pos2.y);
                }
                trailCtx.stroke();
            }
        }
    } else {
        // Clear trails when disabled
        trailCtx.fillStyle = '#111';
        trailCtx.fillRect(0, 0, trailCanvas.width, trailCanvas.height);
    }

    // Balls layer (ON TOP) - clear and redraw completely fresh, with transparent background
    gl.clearColor(0, 0, 0, 0); // Transparent so we see trails below
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    // Draw all balls fully opaque on top
    for (let ball of balls) {
        let color = ball.getColor();
        gl.uniform2f(centerLoc, ball.x, ball.y);
        gl.uniform1f(radiusLoc, ball.r);
        gl.uniform3f(colorLoc, color[0], color[1], color[2]);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
    }
}

// Animation loop - simpler approach for consistent 60 FPS
let lastTime = 0;
let frameCount = 0;
let fpsAccumulator = 0;

function animate(time = 0) {
    requestAnimationFrame(animate);

    if (!lastTime) lastTime = time;
    let delta = time - lastTime;

    // Skip frame if delta is too large (tab was inactive)
    if (delta > 100) {
        lastTime = time;
        return;
    }

    lastTime = time;

    // FPS counter
    fpsAccumulator += delta;
    frameCount++;

    if (fpsAccumulator >= 1000) {
        let fps = Math.round(frameCount * 1000 / fpsAccumulator);
        document.getElementById('fps').textContent = fps;
        frameCount = 0;
        fpsAccumulator = 0;
    }

    // Physics and movement
    handleCollisions();

    for (let b of balls) {
        b.move();
    }

    // Render
    render();
}

window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    trailCanvas.width = canvas.width;
    trailCanvas.height = canvas.height;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(resolutionLoc, canvas.width, canvas.height);
    cellSize = Math.max(canvas.width, canvas.height) / GRID_SIZE;
});

animate();
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
