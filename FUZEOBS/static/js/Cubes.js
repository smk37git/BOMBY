/**
 * Cubes Animation - Optimized for Performance
 */
class CubesAnimation {
  constructor(container, options = {}) {
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    if (!this.container) {
      console.warn('CubesAnimation: Container not found');
      return;
    }
    
    this.options = {
      gridSize: options.gridSize || 10,
      maxAngle: options.maxAngle || 45,
      radius: options.radius || 3,
      easing: options.easing || 'power3.out',
      enterDuration: options.enterDuration || 0.25,
      leaveDuration: options.leaveDuration || 0.5,
      borderStyle: options.borderStyle || '1px dashed rgba(255, 255, 255, 0.7)',
      faceColor: options.faceColor || '#000',
      autoAnimate: options.autoAnimate !== false,
      rippleOnClick: options.rippleOnClick !== false,
      rippleColor: options.rippleColor || 'rgba(255, 255, 255, 0.9)',
      rippleSpeed: options.rippleSpeed || 2
    };
    
    this.cubes = [];
    this.userActive = false;
    this.simPos = { x: 0, y: 0 };
    this.simTarget = { x: 0, y: 0 };
    this.animationFrame = null;
    this.idleTimer = null;
    this.lastPointerTime = 0;
    this.throttleMs = 16;
    
    this.init();
  }

  init() {
    this.createDOM();
    this.bindEvents();
    if (this.options.autoAnimate) {
      requestAnimationFrame(() => this.startAutoAnimation());
    }
  }

  createDOM() {
    const { gridSize, borderStyle, faceColor } = this.options;
    
    this.container.innerHTML = '';
    
    this.wrapper = document.createElement('div');
    this.wrapper.className = 'default-animation';
    this.wrapper.style.setProperty('--cube-face-border', borderStyle);
    this.wrapper.style.setProperty('--cube-face-bg', faceColor);
    
    this.scene = document.createElement('div');
    this.scene.className = 'default-animation--scene';
    this.scene.style.gridTemplateColumns = `repeat(${gridSize}, 1fr)`;
    this.scene.style.gridTemplateRows = `repeat(${gridSize}, 1fr)`;
    
    const fragment = document.createDocumentFragment();
    
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
        
        fragment.appendChild(cube);
        this.cubes.push({ el: cube, row: r, col: c, rotX: 0, rotY: 0 });
      }
    }
    
    this.scene.appendChild(fragment);
    this.wrapper.appendChild(this.scene);
    this.container.appendChild(this.wrapper);
  }

  tiltAt(rowCenter, colCenter) {
    const { radius, maxAngle, enterDuration, leaveDuration } = this.options;
    
    this.cubes.forEach(cube => {
      const dist = Math.hypot(cube.row - rowCenter, cube.col - colCenter);
      
      let targetX = 0, targetY = 0;
      if (dist <= radius) {
        const pct = 1 - dist / radius;
        const angle = pct * maxAngle;
        targetX = -angle;
        targetY = angle;
      }
      
      if (cube.rotX !== targetX || cube.rotY !== targetY) {
        cube.rotX = targetX;
        cube.rotY = targetY;
        const dur = (targetX === 0 && targetY === 0) ? leaveDuration : enterDuration;
        
        if (typeof gsap !== 'undefined') {
          gsap.to(cube.el, {
            duration: dur,
            rotateX: targetX,
            rotateY: targetY,
            ease: 'power3.out',
            overwrite: 'auto'
          });
        } else {
          cube.el.style.transition = `transform ${dur}s cubic-bezier(0.4, 0, 0.2, 1)`;
          cube.el.style.transform = `rotateX(${targetX}deg) rotateY(${targetY}deg)`;
        }
      }
    });
  }

  resetAll() {
    this.cubes.forEach(cube => {
      if (cube.rotX !== 0 || cube.rotY !== 0) {
        cube.rotX = 0;
        cube.rotY = 0;
        if (typeof gsap !== 'undefined') {
          gsap.to(cube.el, { duration: this.options.leaveDuration, rotateX: 0, rotateY: 0, ease: 'power3.out' });
        } else {
          cube.el.style.transition = `transform ${this.options.leaveDuration}s cubic-bezier(0.4, 0, 0.2, 1)`;
          cube.el.style.transform = 'rotateX(0) rotateY(0)';
        }
      }
    });
  }

  onPointerMove(e) {
    const now = performance.now();
    if (now - this.lastPointerTime < this.throttleMs) return;
    this.lastPointerTime = now;
    
    this.userActive = true;
    clearTimeout(this.idleTimer);
    
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const cube = el?.closest('.cube');
    
    if (cube) {
      const row = +cube.dataset.row;
      const col = +cube.dataset.col;
      this.tiltAt(row, col);
    }
    
    this.idleTimer = setTimeout(() => { this.userActive = false; }, 2000);
  }

  onClick(e) {
    if (!this.options.rippleOnClick || typeof gsap === 'undefined') return;
    
    const { faceColor, rippleColor, rippleSpeed } = this.options;
    
    // Use elementFromPoint like original
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const cube = el?.closest('.cube');
    if (!cube) return;
    
    const rowHit = +cube.dataset.row;
    const colHit = +cube.dataset.col;
    
    const spreadDelay = 0.08 / rippleSpeed;
    const animDuration = 0.2 / rippleSpeed;
    const holdTime = 0.3 / rippleSpeed;
    
    this.cubes.forEach(c => {
      const dist = Math.hypot(c.row - rowHit, c.col - colHit);
      const delay = dist * spreadDelay;
      const faces = c.el.querySelectorAll('.cube-face');
      
      gsap.to(faces, { 
        borderColor: rippleColor, 
        backgroundColor: rippleColor,
        duration: animDuration, 
        delay
      });
      gsap.to(faces, { 
        borderColor: 'rgba(255, 255, 255, 0.7)', 
        backgroundColor: faceColor,
        duration: animDuration, 
        delay: delay + animDuration + holdTime
      });
    });
  }

  startAutoAnimation() {
    const { gridSize } = this.options;
    this.simPos = { x: Math.random() * gridSize, y: Math.random() * gridSize };
    this.simTarget = { x: Math.random() * gridSize, y: Math.random() * gridSize };
    
    const loop = () => {
      if (!this.userActive) {
        const speed = 0.012;
        this.simPos.x += (this.simTarget.x - this.simPos.x) * speed;
        this.simPos.y += (this.simTarget.y - this.simPos.y) * speed;
        this.tiltAt(this.simPos.y, this.simPos.x);
        
        if (Math.hypot(this.simPos.x - this.simTarget.x, this.simPos.y - this.simTarget.y) < 0.5) {
          this.simTarget = { x: Math.random() * gridSize, y: Math.random() * gridSize };
        }
      }
      this.animationFrame = requestAnimationFrame(loop);
    };
    this.animationFrame = requestAnimationFrame(loop);
  }

  bindEvents() {
    this.scene.addEventListener('pointermove', e => this.onPointerMove(e), { passive: true });
    this.scene.addEventListener('pointerleave', () => this.resetAll());
    this.scene.addEventListener('click', e => this.onClick(e));
    
    this.scene.addEventListener('touchmove', e => {
      if (e.touches[0]) this.onPointerMove(e.touches[0]);
    }, { passive: true });
    this.scene.addEventListener('touchend', () => this.resetAll());
  }

  destroy() {
    cancelAnimationFrame(this.animationFrame);
    clearTimeout(this.idleTimer);
    this.container.innerHTML = '';
  }
}

// Auto-init if container exists
if (typeof window !== 'undefined') {
  window.CubesAnimation = CubesAnimation;
}