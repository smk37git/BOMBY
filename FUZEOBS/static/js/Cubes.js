/**
 * Cubes Animation - Full Width Version
 * Requires GSAP: <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
 */
class CubesAnimation {
  constructor(container, options = {}) {
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    this.options = {
      gridSize: options.gridSize || 10,
      maxAngle: options.maxAngle || 45,
      radius: options.radius || 3,
      easing: options.easing || 'power3.out',
      enterDuration: options.enterDuration || 0.3,
      leaveDuration: options.leaveDuration || 0.6,
      borderStyle: options.borderStyle || '1px dashed rgba(255, 255, 255, 0.7)',
      faceColor: options.faceColor || '#000',
      autoAnimate: options.autoAnimate !== false,
      rippleOnClick: options.rippleOnClick !== false,
      rippleColor: options.rippleColor || 'rgba(255, 255, 255, 0.9)',
      rippleSpeed: options.rippleSpeed || 2,
      cellGap: options.cellGap !== undefined ? options.cellGap : 0
    };
    
    this.userActive = false;
    this.simPos = { x: 0, y: 0 };
    this.simTarget = { x: 0, y: 0 };
    this.animationFrame = null;
    this.idleTimer = null;
    
    this.init();
  }

  init() {
    this.createDOM();
    this.bindEvents();
    if (this.options.autoAnimate) this.startAutoAnimation();
  }

  createDOM() {
    const { gridSize, borderStyle, faceColor, cellGap } = this.options;
    
    this.container.innerHTML = '';
    
    // Create wrapper like original React structure
    this.wrapper = document.createElement('div');
    this.wrapper.className = 'default-animation';
    this.wrapper.style.setProperty('--cube-face-border', borderStyle);
    this.wrapper.style.setProperty('--cube-face-bg', faceColor);
    
    this.scene = document.createElement('div');
    this.scene.className = 'default-animation--scene';
    this.scene.style.gridTemplateColumns = `repeat(${gridSize}, 1fr)`;
    this.scene.style.gridTemplateRows = `repeat(${gridSize}, 1fr)`;
    
    for (let r = 0; r < gridSize; r++) {
      for (let c = 0; c < gridSize; c++) {
        const cube = document.createElement('div');
        cube.className = 'cube';
        cube.dataset.row = r;
        cube.dataset.col = c;
        
        ['top', 'bottom', 'left', 'right', 'front', 'back'].forEach(face => {
          const faceEl = document.createElement('div');
          faceEl.className = `cube-face cube-face--${face}`;
          cube.appendChild(faceEl);
        });
        
        this.scene.appendChild(cube);
      }
    }
    
    this.wrapper.appendChild(this.scene);
    this.container.appendChild(this.wrapper);
  }

  tiltAt(rowCenter, colCenter) {
    const { radius, maxAngle, enterDuration, leaveDuration, easing } = this.options;
    
    this.scene.querySelectorAll('.cube').forEach(cube => {
      const r = +cube.dataset.row;
      const c = +cube.dataset.col;
      const dist = Math.hypot(r - rowCenter, c - colCenter);
      
      if (dist <= radius) {
        const pct = 1 - dist / radius;
        const angle = pct * maxAngle;
        gsap.to(cube, {
          duration: enterDuration,
          ease: easing,
          overwrite: true,
          rotateX: -angle,
          rotateY: angle
        });
      } else {
        gsap.to(cube, {
          duration: leaveDuration,
          ease: 'power3.out',
          overwrite: true,
          rotateX: 0,
          rotateY: 0
        });
      }
    });
  }

  resetAll() {
    this.scene.querySelectorAll('.cube').forEach(cube => {
      gsap.to(cube, {
        duration: this.options.leaveDuration,
        rotateX: 0,
        rotateY: 0,
        ease: 'power3.out'
      });
    });
  }

  onPointerMove(e) {
    this.userActive = true;
    clearTimeout(this.idleTimer);
    
    // Find the actual element under cursor
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const cube = el?.closest('.cube');
    
    if (cube) {
      const row = +cube.dataset.row;
      const col = +cube.dataset.col;
      cancelAnimationFrame(this.moveFrame);
      this.moveFrame = requestAnimationFrame(() => this.tiltAt(row, col));
    }
    
    this.idleTimer = setTimeout(() => { this.userActive = false; }, 3000);
  }

  onClick(e) {
    if (!this.options.rippleOnClick) return;
    
    const { gridSize, faceColor, rippleColor, rippleSpeed } = this.options;
    
    const clientX = e.clientX || (e.touches?.[0]?.clientX);
    const clientY = e.clientY || (e.touches?.[0]?.clientY);
    
    // Find actual cube under click
    const el = document.elementFromPoint(clientX, clientY);
    const cube = el?.closest('.cube');
    if (!cube) return;
    
    const rowHit = +cube.dataset.row;
    const colHit = +cube.dataset.col;
    
    const spreadDelay = 0.12 / rippleSpeed;
    const animDuration = 0.25 / rippleSpeed;
    const holdTime = 0.4 / rippleSpeed;
    
    const rings = {};
    this.scene.querySelectorAll('.cube').forEach(cube => {
      const r = +cube.dataset.row;
      const c = +cube.dataset.col;
      const dist = Math.hypot(r - rowHit, c - colHit);
      const ring = Math.round(dist);
      if (!rings[ring]) rings[ring] = [];
      rings[ring].push(cube);
    });
    
    Object.keys(rings).map(Number).sort((a, b) => a - b).forEach(ring => {
      const delay = ring * spreadDelay;
      const faces = rings[ring].flatMap(cube => Array.from(cube.querySelectorAll('.cube-face')));
      
      gsap.to(faces, { 
        borderColor: rippleColor, 
        backgroundColor: rippleColor,
        duration: animDuration, 
        delay, 
        ease: 'power3.out' 
      });
      gsap.to(faces, { 
        borderColor: 'rgba(255, 255, 255, 0.7)', 
        backgroundColor: faceColor,
        duration: animDuration, 
        delay: delay + animDuration + holdTime, 
        ease: 'power3.out' 
      });
    });
  }

  startAutoAnimation() {
    const { gridSize } = this.options;
    this.simPos = { x: Math.random() * gridSize, y: Math.random() * gridSize };
    this.simTarget = { x: Math.random() * gridSize, y: Math.random() * gridSize };
    
    const loop = () => {
      if (!this.userActive) {
        const speed = 0.015;
        this.simPos.x += (this.simTarget.x - this.simPos.x) * speed;
        this.simPos.y += (this.simTarget.y - this.simPos.y) * speed;
        this.tiltAt(this.simPos.y, this.simPos.x);
        
        if (Math.hypot(this.simPos.x - this.simTarget.x, this.simPos.y - this.simTarget.y) < 0.1) {
          this.simTarget = { x: Math.random() * gridSize, y: Math.random() * gridSize };
        }
      }
      this.animationFrame = requestAnimationFrame(loop);
    };
    this.animationFrame = requestAnimationFrame(loop);
  }

  bindEvents() {
    // Bind to scene like original React code
    this.scene.addEventListener('pointermove', e => this.onPointerMove(e));
    this.scene.addEventListener('pointerleave', () => this.resetAll());
    this.scene.addEventListener('click', e => this.onClick(e));
    
    this.scene.addEventListener('touchmove', e => {
      e.preventDefault();
      this.onPointerMove(e.touches[0]);
    }, { passive: false });
    this.scene.addEventListener('touchend', () => this.resetAll());
  }

  destroy() {
    cancelAnimationFrame(this.animationFrame);
    cancelAnimationFrame(this.moveFrame);
    clearTimeout(this.idleTimer);
    this.container.innerHTML = '';
  }
}