/**
 * CardSwap Animation - Vanilla JS for FuzeOBS
 * Shows only 5 cards at a time
 */
class CardSwap {
  constructor(container, options = {}) {
    this.container = typeof container === 'string' ? document.querySelector(container) : container;
    this.options = {
      cardDistance: options.cardDistance || 30,
      verticalDistance: options.verticalDistance || 28,
      delay: options.delay || 4000,
      pauseOnHover: options.pauseOnHover !== false,
      skewAmount: options.skewAmount || 0,
      width: options.width || 420,
      height: options.height || 320,
      visibleCards: options.visibleCards || 5,
    };
    
    this.cards = [];
    this.order = [];
    this.interval = null;
    this.isPaused = false;
    this.isAnimating = false;
    
    this.init();
  }
  
  init() {
    this.container.classList.add('card-swap-container');
    this.container.style.width = this.options.width + 'px';
    this.container.style.height = this.options.height + 'px';
    
    this.cards = Array.from(this.container.querySelectorAll('.swap-card'));
    this.order = this.cards.map((_, i) => i);
    
    this.cards.forEach((card, i) => {
      this.placeCard(card, i, false);
    });
    
    setTimeout(() => this.swap(), 500);
    this.interval = setInterval(() => {
      if (!this.isPaused && !this.isAnimating) this.swap();
    }, this.options.delay);
    
    if (this.options.pauseOnHover) {
      this.container.addEventListener('mouseenter', () => this.isPaused = true);
      this.container.addEventListener('mouseleave', () => this.isPaused = false);
    }
  }
  
  makeSlot(i) {
    const { cardDistance, verticalDistance, visibleCards } = this.options;
    const isVisible = i < visibleCards;
    return {
      x: isVisible ? i * cardDistance : (visibleCards - 1) * cardDistance,
      y: isVisible ? -i * verticalDistance : -(visibleCards - 1) * verticalDistance,
      z: isVisible ? -i * cardDistance * 0.6 : -(visibleCards - 1) * cardDistance * 0.6 - 50,
      zIndex: this.cards.length - i,
      opacity: isVisible ? 1 : 0
    };
  }
  
  placeCard(card, index, animate = true) {
    const slot = this.makeSlot(index);
    const transform = `translate(-50%, -50%) translate3d(${slot.x}px, ${slot.y}px, ${slot.z}px) skewY(${this.options.skewAmount}deg)`;
    
    if (animate) {
      card.style.transition = 'transform 0.7s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.5s ease';
    } else {
      card.style.transition = 'none';
    }
    
    card.style.transform = transform;
    card.style.zIndex = slot.zIndex;
    card.style.opacity = slot.opacity;
  }
  
  swap() {
    if (this.order.length < 2 || this.isAnimating) return;
    this.isAnimating = true;
    
    const [front, ...rest] = this.order;
    const frontCard = this.cards[front];
    const { cardDistance, verticalDistance, visibleCards } = this.options;
    
    // Animate front card moving UP and BACK (behind the stack)
    const backX = (visibleCards) * cardDistance;
    const backY = -(visibleCards) * verticalDistance;
    const backZ = -(visibleCards) * cardDistance * 0.8;
    
    frontCard.style.transition = 'transform 0.6s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.4s ease';
    frontCard.style.opacity = '0';
    frontCard.style.transform = `translate(-50%, -50%) translate3d(${backX}px, ${backY}px, ${backZ}px)`;
    frontCard.style.zIndex = 0;
    
    // Promote visible cards forward
    setTimeout(() => {
      rest.forEach((idx, i) => {
        this.placeCard(this.cards[idx], i, true);
      });
    }, 150);
    
    // Position front card at very back (hidden)
    setTimeout(() => {
      const backIndex = this.cards.length - 1;
      const backSlot = this.makeSlot(backIndex);
      frontCard.style.transition = 'none';
      frontCard.style.transform = `translate(-50%, -50%) translate3d(${backSlot.x}px, ${backSlot.y}px, ${backSlot.z}px)`;
      frontCard.style.zIndex = backSlot.zIndex;
      frontCard.style.opacity = '0';
    }, 600);
    
    setTimeout(() => {
      this.order = [...rest, front];
      this.isAnimating = false;
    }, 700);
  }
  
  // Bring specific card to front by tab id
  showCard(tabId) {
    if (this.isAnimating) return;
    
    const cardIndex = this.cards.findIndex(c => c.dataset.tab === tabId);
    if (cardIndex === -1) return;
    
    const orderIndex = this.order.indexOf(cardIndex);
    if (orderIndex === 0) return; // Already at front
    
    this.isAnimating = true;
    
    // Reorder: move target to front
    const newOrder = [cardIndex, ...this.order.filter(i => i !== cardIndex)];
    
    // Animate all cards to new positions
    newOrder.forEach((idx, i) => {
      this.placeCard(this.cards[idx], i, true);
    });
    
    setTimeout(() => {
      this.order = newOrder;
      this.isAnimating = false;
    }, 700);
  }
  
  destroy() {
    if (this.interval) clearInterval(this.interval);
  }
}

const FUZEOBS_TABS = [
  { id: 'detection', title: 'Detection', description: 'Auto-detect CPU, GPU, RAM, monitors, and encoders.', features: ['Hardware scanning', 'Encoder detection', 'Performance rating'] },
  { id: 'configuration', title: 'Configuration', description: 'Select platform, quality presets, and output modes.', features: ['Platform selection', 'Quality presets', 'Output modes'] },
  { id: 'optimization', title: 'Optimization', description: 'Fine-tune encoder settings, bitrate, and resolution.', features: ['Encoder tuning', 'Bitrate optimization', 'Resolution scaling'] },
  { id: 'audio', title: 'Audio', description: 'Configure microphones, filters, and noise suppression.', features: ['Device selection', 'Audio filters', 'Noise suppression'] },
  { id: 'scenes', title: 'Scenes', description: 'Pre-built scene templates for gaming, IRL, podcasts.', features: ['Template library', 'Source layouts', 'Auto-setup'] },
  { id: 'tools', title: 'Tools', description: 'Stream widgets: alerts, chat boxes, goals, donations.', features: ['Alert boxes', 'Chat overlays', 'Goal bars'] },
  { id: 'plugins', title: 'Plugins', description: 'One-click install for essential OBS plugins.', features: ['Plugin manager', 'Auto-install', 'Compatibility check'] },
  { id: 'documentation', title: 'Docs', description: 'Built-in guides, tutorials, and best practices.', features: ['Setup guides', 'Troubleshooting', 'Best practices'] },
  { id: 'benchmark', title: 'Benchmark', description: 'Real-time performance testing and stress analysis.', features: ['FPS testing', 'Encoder stress test', 'Heat monitoring'] },
  { id: 'fuze-ai', title: 'Fuze-AI', description: 'AI assistant for troubleshooting and optimization.', features: ['Live chat support', 'Config analysis', 'Recommendations'] }
];

/**
 * Generate card HTML with window-style title bar
 * For images: useImages=true, 800x600px, named: detection.png, etc.
 */
function generateTabCards(useImages = false, imagePath = '/static/images/fuzeobs/tabs/') {
  return FUZEOBS_TABS.map((tab, index) => {
    const titleBar = `
      <div class="swap-card-titlebar">
        <div class="titlebar-dots">
          <span></span><span></span><span></span>
        </div>
        <span class="titlebar-title">${String(index + 1).padStart(2, '0')} - ${tab.title}</span>
      </div>
    `;
    
    if (useImages) {
      return `
        <div class="swap-card swap-card-image" data-tab="${tab.id}">
          ${titleBar}
          <div class="swap-card-body">
            <img src="${imagePath}${tab.id}.png" alt="${tab.title}" onerror="this.parentElement.innerHTML='<div class=\\'swap-card-fallback\\'><h3>${tab.title}</h3><p>${tab.description}</p></div>'" />
          </div>
        </div>
      `;
    }
    return `
      <div class="swap-card" data-tab="${tab.id}">
        ${titleBar}
        <div class="swap-card-body">
          <h3 class="swap-card-title">${tab.title}</h3>
          <p class="swap-card-desc">${tab.description}</p>
          <ul class="swap-card-features">
            ${tab.features.map(f => `<li>${f}</li>`).join('')}
          </ul>
        </div>
      </div>
    `;
  }).join('');
}