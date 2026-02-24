from flask import Flask, Response

app = Flask(__name__)

@app.route("/")
def home():
    return Response("""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Chaos Rainbow System</title>
<style>
html,body{
    margin:0;
    padding:0;
    overflow:hidden;
    background:black;
}
canvas{display:block;}
#ui{
    position:fixed;
    top:10px;
    width:100%;
    text-align:center;
    font-family:Arial;
    font-weight:bold;
    font-size:14px;
    color:#ffffff;
    user-select:none;
}
.button{ margin:0 10px; cursor:pointer; }
#counter{
    position:fixed;
    bottom:10px;
    right:15px;
    color:white;
    font-family:Arial;
    font-size:14px;
}
</style>
</head>
<body>

<div id="ui">
<span class="button" id="normalBtn">NORMAL</span>
<span class="button" id="obamaBtn">OBAMA</span>
<span class="button" id="trumpBtn">TRUMP</span>
<span class="button" id="clearBtn">CLEAR</span>
<span class="button" id="holeBtn">BLACK HOLE</span>
</div>

<div id="counter">Balls: 0</div>
<canvas></canvas>

<script>
const canvas = document.querySelector("canvas");
const ctx = canvas.getContext("2d");

function resize(){
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}
resize();
window.onresize = resize;

// ---------------- CONFIG ----------------
const START_BALLS = 10;
const BASE_R = 22;
const MERGE_CHANCE = 0.12;
const BOUNCE_GAIN = 1.15;
const SPLIT_MIN = 1000;
const SPLIT_MAX = 5000;
const EXPLODE_PARTS = 10;
const NET_GAIN = 2;
const MERGE_GRACE = 700;
const MAX_R = 75;
const SWIPE_MULT = 1.0;
const MAX_SWIPE_SPEED = 2200;
const CORNER_THRESHOLD = 40;
// ----------------------------------------

let balls = [];
let nextId = 0;
let globalTexture = null;
let blackHole = false;

let swipeStart = null;
let swipeTime = 0;

// Images
const obamaImg = new Image();
obamaImg.src = "https://upload.wikimedia.org/wikipedia/commons/8/8d/President_Barack_Obama.jpg";

const trumpImg = new Image();
trumpImg.src = "https://upload.wikimedia.org/wikipedia/commons/5/56/Donald_Trump_official_portrait.jpg";

function spawn(x,y,vx,vy,r=BASE_R,chaos=false){
    balls.push({
        id: nextId++,
        x,y,vx,vy,r,
        splitAt:null,
        noMergeUntil:0,
        chaos:chaos,
        hue:Math.random()*360
    });
}

function rand(a,b){ return Math.random()*(b-a)+a; }

for(let i=0;i<START_BALLS;i++){
    spawn(
        Math.random()*canvas.width,
        Math.random()*canvas.height,
        (Math.random()-0.5)*500,
        (Math.random()-0.5)*500
    );
}

function update(dt){
    const now = performance.now();

    for(let b of balls){

        if(blackHole){
            let dx = canvas.width/2 - b.x;
            let dy = canvas.height/2 - b.y;
            b.vx += dx * 0.5 * dt;
            b.vy += dy * 0.5 * dt;
        }

        b.x += b.vx * dt;
        b.y += b.vy * dt;

        let bounced = false;

        if(b.x < b.r){ b.x = b.r; b.vx *= -1; bounced = true; }
        if(b.x > canvas.width - b.r){ b.x = canvas.width - b.r; b.vx *= -1; bounced = true; }
        if(b.y < b.r){ b.y = b.r; b.vy *= -1; bounced = true; }
        if(b.y > canvas.height - b.r){ b.y = canvas.height - b.r; b.vy *= -1; bounced = true; }

        if(bounced){
            b.vx *= BOUNCE_GAIN;
            b.vy *= BOUNCE_GAIN;
        }

        // corner explosion trigger
        if(!b.chaos){
            let nearLeft = b.x < CORNER_THRESHOLD;
            let nearRight = b.x > canvas.width - CORNER_THRESHOLD;
            let nearTop = b.y < CORNER_THRESHOLD;
            let nearBottom = b.y > canvas.height - CORNER_THRESHOLD;

            if((nearLeft && nearTop) ||
               (nearRight && nearTop) ||
               (nearLeft && nearBottom) ||
               (nearRight && nearBottom)){

                createChaosBall(b);
                balls = balls.filter(ball => ball.id !== b.id);
                break;
            }
        }

        b.hue += 200 * dt;
        if(b.hue > 360) b.hue -= 360;
    }

    handleMerge(now);
    handleSplit(now);
}

function createChaosBall(source){
    spawn(
        canvas.width/2,
        canvas.height/2,
        (Math.random()-0.5)*1200,
        (Math.random()-0.5)*1200,
        120,
        true
    );
}

function handleMerge(now){
    let removed = new Set();
    let created = [];

    for(let i=0;i<balls.length;i++){
        if(removed.has(i)) continue;

        for(let j=i+1;j<balls.length;j++){
            if(removed.has(j)) continue;

            let a=balls[i], b=balls[j];
            if(a.chaos || b.chaos) continue;
            if(now < a.noMergeUntil || now < b.noMergeUntil) continue;

            let dx=a.x-b.x;
            let dy=a.y-b.y;
            let dist=Math.hypot(dx,dy);

            if(dist < a.r + b.r && Math.random() < MERGE_CHANCE){

                let merged={
                    id: nextId++,
                    x:(a.x+b.x)/2,
                    y:(a.y+b.y)/2,
                    vx:(a.vx+b.vx)/2,
                    vy:(a.vy+b.vy)/2,
                    r:Math.sqrt(a.r*a.r + b.r*b.r),
                    splitAt: now + rand(SPLIT_MIN, SPLIT_MAX),
                    noMergeUntil: now + MERGE_GRACE,
                    chaos:false,
                    hue:Math.random()*360
                };

                created.push(merged);
                removed.add(i);
                removed.add(j);
                break;
            }
        }
    }

    balls = balls.filter((_,i)=>!removed.has(i)).concat(created);
}

function handleSplit(now){
    let next=[];

    for(let b of balls){
        if(!b.chaos && ((b.splitAt && now>=b.splitAt) || b.r > MAX_R)){

            let count = EXPLODE_PARTS + NET_GAIN;

            for(let i=0;i<count;i++){
                let ang=Math.random()*Math.PI*2;
                let sp=200+Math.random()*200;

                next.push({
                    id: nextId++,
                    x:b.x,
                    y:b.y,
                    vx:b.vx + Math.cos(ang)*sp,
                    vy:b.vy + Math.sin(ang)*sp,
                    r:BASE_R,
                    splitAt:null,
                    noMergeUntil: now + MERGE_GRACE,
                    chaos:false,
                    hue:Math.random()*360
                });
            }

        } else {
            next.push(b);
        }
    }

    balls = next;
}

function draw(){
    ctx.clearRect(0,0,canvas.width,canvas.height);

    for(let b of balls){
        ctx.beginPath();
        ctx.arc(b.x,b.y,b.r,0,Math.PI*2);

        if(globalTexture){
            ctx.save();
            ctx.clip();
            ctx.drawImage(globalTexture,b.x-b.r,b.y-b.r,b.r*2,b.r*2);
            ctx.restore();
        }else{
            ctx.fillStyle = "hsl(" + b.hue + ",100%,50%)";
            ctx.fill();
        }
    }

    document.getElementById("counter").innerText="Balls: " + balls.length;
}

let last=performance.now();
function loop(now){
    let dt=(now-last)/1000;
    last=now;
    update(dt);
    draw();
    requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

function handleRelease(x,y){
    if(!swipeStart) return;

    let dx = x - swipeStart.x;
    let dy = y - swipeStart.y;
    let dt = (performance.now() - swipeTime)/1000;
    if(dt <= 0) dt = 0.001;

    let vx = (dx/dt) * SWIPE_MULT;
    let vy = (dy/dt) * SWIPE_MULT;

    let speed = Math.hypot(vx,vy);
    if(speed > MAX_SWIPE_SPEED){
        let scale = MAX_SWIPE_SPEED / speed;
        vx *= scale;
        vy *= scale;
    }

    spawn(swipeStart.x, swipeStart.y, vx, vy);
    swipeStart = null;
}

canvas.addEventListener("mousedown", e=>{
    swipeStart = {x:e.clientX, y:e.clientY};
    swipeTime = performance.now();
});
canvas.addEventListener("mouseup", e=>{
    handleRelease(e.clientX, e.clientY);
});

canvas.addEventListener("touchstart", e=>{
    let t=e.touches[0];
    swipeStart = {x:t.clientX, y:t.clientY};
    swipeTime = performance.now();
});
canvas.addEventListener("touchend", e=>{
    let t=e.changedTouches[0];
    handleRelease(t.clientX, t.clientY);
});

normalBtn.onclick=()=>globalTexture=null;
obamaBtn.onclick=()=>globalTexture=obamaImg;
trumpBtn.onclick=()=>globalTexture=trumpImg;
clearBtn.onclick=()=>balls=[];
holeBtn.onclick=()=>blackHole=!blackHole;

</script>
</body>
</html>
""", mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)