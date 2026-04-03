const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const scoreEl = document.getElementById("score");
const highScoreEl = document.getElementById("highScore");
const restartBtn = document.getElementById("restartBtn");
const pauseBtn = document.getElementById("pauseBtn");

const GRID_SIZE = 20;
const CELL = canvas.width / GRID_SIZE;
const TICK_MS = 120;

const DIRS = {
  ArrowUp: { x: 0, y: -1 },
  ArrowDown: { x: 0, y: 1 },
  ArrowLeft: { x: -1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
  w: { x: 0, y: -1 },
  s: { x: 0, y: 1 },
  a: { x: -1, y: 0 },
  d: { x: 1, y: 0 },
};

function createInitialState(rng = Math.random) {
  const mid = Math.floor(GRID_SIZE / 2);
  const snake = [
    { x: mid, y: mid },
    { x: mid - 1, y: mid },
    { x: mid - 2, y: mid },
  ];
  const food = randomEmptyCell(snake, rng);
  return {
    snake,
    dir: { x: 1, y: 0 },
    pendingDir: { x: 1, y: 0 },
    food,
    score: 0,
    isGameOver: false,
    isPaused: false,
  };
}

function randomEmptyCell(snake, rng) {
  const occupied = new Set(snake.map((p) => `${p.x},${p.y}`));
  let x = 0;
  let y = 0;
  do {
    x = Math.floor(rng() * GRID_SIZE);
    y = Math.floor(rng() * GRID_SIZE);
  } while (occupied.has(`${x},${y}`));
  return { x, y };
}

function isOpposite(a, b) {
  return a.x + b.x === 0 && a.y + b.y === 0;
}

function advanceState(state, rng = Math.random) {
  if (state.isGameOver || state.isPaused) return state;

  const nextDir = isOpposite(state.pendingDir, state.dir)
    ? state.dir
    : state.pendingDir;
  const head = state.snake[0];
  const nextHead = { x: head.x + nextDir.x, y: head.y + nextDir.y };

  const hitsWall =
    nextHead.x < 0 ||
    nextHead.y < 0 ||
    nextHead.x >= GRID_SIZE ||
    nextHead.y >= GRID_SIZE;

  const hitsSelf = state.snake.some(
    (segment) => segment.x === nextHead.x && segment.y === nextHead.y
  );

  if (hitsWall || hitsSelf) {
    return { ...state, dir: nextDir, isGameOver: true };
  }

  const ateFood = nextHead.x === state.food.x && nextHead.y === state.food.y;
  const nextSnake = [nextHead, ...state.snake];

  if (!ateFood) {
    nextSnake.pop();
  }

  const nextFood = ateFood ? randomEmptyCell(nextSnake, rng) : state.food;

  return {
    ...state,
    snake: nextSnake,
    dir: nextDir,
    food: nextFood,
    score: ateFood ? state.score + 1 : state.score,
  };
}

let state = createInitialState();
let highScore = Number(localStorage.getItem("snakeHighScore") || 0);

function setScoreDisplay() {
  scoreEl.textContent = String(state.score);
  highScoreEl.textContent = String(highScore);
}

function resetGame() {
  state = createInitialState();
  setScoreDisplay();
  pauseBtn.textContent = "Pause (Space)";
}

function togglePause() {
  if (state.isGameOver) return;
  state = { ...state, isPaused: !state.isPaused };
  pauseBtn.textContent = state.isPaused ? "Resume (Space)" : "Pause (Space)";
}

function handleDirectionInput(dir) {
  state = { ...state, pendingDir: dir };
}

function drawGrid() {
  ctx.strokeStyle = "#d7cdbb";
  ctx.lineWidth = 1;
  for (let i = 0; i <= GRID_SIZE; i += 1) {
    ctx.beginPath();
    ctx.moveTo(i * CELL, 0);
    ctx.lineTo(i * CELL, canvas.height);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(0, i * CELL);
    ctx.lineTo(canvas.width, i * CELL);
    ctx.stroke();
  }
}

function drawCell(x, y, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
}

function render() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawGrid();

  state.snake.forEach((segment, index) => {
    drawCell(segment.x, segment.y, index === 0 ? "#0f4d2b" : "#1b6a3d");
  });

  drawCell(state.food.x, state.food.y, "#c0382b");

  if (state.isGameOver) {
    ctx.fillStyle = "rgba(31,31,31,0.75)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#fffaf0";
    ctx.font = "bold 24px Georgia";
    ctx.textAlign = "center";
    ctx.fillText("Game Over", canvas.width / 2, canvas.height / 2 - 8);
    ctx.font = "16px Georgia";
    ctx.fillText("Press R to restart", canvas.width / 2, canvas.height / 2 + 20);
  } else if (state.isPaused) {
    ctx.fillStyle = "rgba(31,31,31,0.5)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#fffaf0";
    ctx.font = "bold 20px Georgia";
    ctx.textAlign = "center";
    ctx.fillText("Paused", canvas.width / 2, canvas.height / 2);
  }
}

function tick() {
  state = advanceState(state);
  if (state.score > highScore) {
    highScore = state.score;
    localStorage.setItem("snakeHighScore", String(highScore));
  }
  setScoreDisplay();
  render();
}

setScoreDisplay();
render();
const interval = setInterval(tick, TICK_MS);

window.addEventListener("keydown", (event) => {
  if (event.key === "r" || event.key === "R") {
    resetGame();
    return;
  }
  if (event.key === " ") {
    togglePause();
    return;
  }
  const dir = DIRS[event.key];
  if (dir) {
    event.preventDefault();
    handleDirectionInput(dir);
  }
});

restartBtn.addEventListener("click", resetGame);
pauseBtn.addEventListener("click", togglePause);

canvas.addEventListener("click", () => {
  if (state.isGameOver) resetGame();
});

