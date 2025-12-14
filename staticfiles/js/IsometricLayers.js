/**
 * Isometric Layers - Lambda-style animated layer graphic
 * For FuzeOBS
 */

class IsometricLayers {
    constructor(container, options = {}) {
        this.container = container;
        this.activeLayer = options.initialLayer || 0;
        this.layers = options.layers || [
            { id: 'deployment', label: 'Deployment', sideLabel: 'CORE' },
            { id: 'setup', label: 'Setup', sideLabel: 'CUSTOMIZE' },
            { id: 'extras', label: 'Extras', sideLabel: 'EXTEND' },
            { id: 'ai', label: 'AI Enhancements', sideLabel: 'INTELLIGENT' }
        ];
        this.init();
    }

    init() {
        this.render();
        this.attachEvents();
        this.setActive(this.activeLayer, false);
    }

    render() {
        this.container.innerHTML = `
            <div class="iso-layers-wrapper">
                <svg class="iso-layers-svg" viewBox="0 0 500 400" preserveAspectRatio="xMidYMid meet">
                    <defs>
                        <linearGradient id="layerGradient0" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:0.8"/>
                            <stop offset="100%" style="stop-color:#1d4ed8;stop-opacity:0.6"/>
                        </linearGradient>
                        <linearGradient id="layerGradient1" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#8b5cf6;stop-opacity:0.8"/>
                            <stop offset="100%" style="stop-color:#6d28d9;stop-opacity:0.6"/>
                        </linearGradient>
                        <linearGradient id="layerGradient2" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#f59e0b;stop-opacity:0.8"/>
                            <stop offset="100%" style="stop-color:#d97706;stop-opacity:0.6"/>
                        </linearGradient>
                        <linearGradient id="layerGradient3" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#10b981;stop-opacity:0.8"/>
                            <stop offset="100%" style="stop-color:#059669;stop-opacity:0.6"/>
                        </linearGradient>
                        <filter id="glow">
                            <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                            <feMerge>
                                <feMergeNode in="coloredBlur"/>
                                <feMergeNode in="SourceGraphic"/>
                            </feMerge>
                        </filter>
                    </defs>
                    
                    <!-- Dots/nodes background -->
                    <g class="iso-dots" opacity="0.3">
                        ${this.generateDots()}
                    </g>
                    
                    <!-- Connection lines -->
                    <g class="iso-connections">
                        ${this.generateConnections()}
                    </g>
                    
                    <!-- Layers (bottom to top) -->
                    ${this.layers.map((layer, i) => this.renderLayer(i)).reverse().join('')}
                    
                    <!-- Side labels -->
                    ${this.layers.map((layer, i) => `
                        <text class="iso-side-label" data-layer="${i}" 
                              x="460" y="${320 - i * 70}" 
                              text-anchor="start" opacity="0.3">
                            ${layer.sideLabel}
                        </text>
                    `).join('')}
                </svg>
            </div>
        `;
    }

    generateDots() {
        let dots = '';
        for (let i = 0; i < 8; i++) {
            for (let j = 0; j < 6; j++) {
                const x = 120 + i * 40 + (j % 2) * 20;
                const y = 60 + j * 50;
                dots += `<circle cx="${x}" cy="${y}" r="2" fill="rgba(255,255,255,0.5)"/>`;
            }
        }
        return dots;
    }

    generateConnections() {
        return `
            <line x1="420" y1="110" x2="460" y2="110" stroke="rgba(255,255,255,0.1)" stroke-dasharray="2,4"/>
            <line x1="420" y1="180" x2="460" y2="180" stroke="rgba(255,255,255,0.1)" stroke-dasharray="2,4"/>
            <line x1="420" y1="250" x2="460" y2="250" stroke="rgba(255,255,255,0.1)" stroke-dasharray="2,4"/>
            <line x1="420" y1="320" x2="460" y2="320" stroke="rgba(255,255,255,0.1)" stroke-dasharray="2,4"/>
        `;
    }

    renderLayer(index) {
        const baseY = 280 - index * 70;
        const colors = ['#3b82f6', '#8b5cf6', '#f59e0b', '#10b981'];
        const color = colors[index];
        
        // Isometric box dimensions
        const w = 200;  // width
        const h = 120;  // height (isometric)
        const d = 40;   // depth
        const cx = 250; // center x
        
        return `
            <g class="iso-layer" data-layer="${index}">
                <!-- Top face -->
                <path class="iso-face iso-top" 
                      d="M ${cx} ${baseY - d} 
                         L ${cx + w/2} ${baseY - d + h/4} 
                         L ${cx} ${baseY - d + h/2} 
                         L ${cx - w/2} ${baseY - d + h/4} Z"
                      fill="url(#layerGradient${index})"
                      stroke="${color}"
                      stroke-width="1"/>
                
                <!-- Left face -->
                <path class="iso-face iso-left"
                      d="M ${cx - w/2} ${baseY - d + h/4} 
                         L ${cx} ${baseY - d + h/2} 
                         L ${cx} ${baseY + h/2} 
                         L ${cx - w/2} ${baseY + h/4} Z"
                      fill="${color}"
                      fill-opacity="0.3"
                      stroke="${color}"
                      stroke-width="1"/>
                
                <!-- Right face -->
                <path class="iso-face iso-right"
                      d="M ${cx + w/2} ${baseY - d + h/4} 
                         L ${cx} ${baseY - d + h/2} 
                         L ${cx} ${baseY + h/2} 
                         L ${cx + w/2} ${baseY + h/4} Z"
                      fill="${color}"
                      fill-opacity="0.2"
                      stroke="${color}"
                      stroke-width="1"/>
                
                <!-- Grid lines on top -->
                <g class="iso-grid" opacity="0.3">
                    ${this.renderGridLines(cx, baseY - d, w, h)}
                </g>
                
                <!-- Layer label -->
                <text class="iso-layer-label" 
                      x="${cx}" y="${baseY - d + h/4 + 5}" 
                      text-anchor="middle" 
                      fill="white" 
                      font-size="12"
                      opacity="0.8">
                    ${this.layers[index].label}
                </text>
                
                <!-- Highlight diamond -->
                <path class="iso-highlight"
                      d="M ${cx} ${baseY - d + 15}
                         L ${cx + 15} ${baseY - d + h/4 + 7}
                         L ${cx} ${baseY - d + h/4 + 15}
                         L ${cx - 15} ${baseY - d + h/4 + 7} Z"
                      fill="${color}"
                      fill-opacity="0"
                      stroke="${color}"
                      stroke-width="2"
                      stroke-opacity="0"/>
            </g>
        `;
    }

    renderGridLines(cx, baseY, w, h) {
        let lines = '';
        // Diagonal lines
        for (let i = 1; i < 4; i++) {
            const offset = (w / 4) * i;
            lines += `
                <line x1="${cx - w/2 + offset/2}" y1="${baseY + h/8 * i}" 
                      x2="${cx + offset/2}" y2="${baseY + h/2 - h/8 * (4-i)}" 
                      stroke="white" stroke-width="0.5"/>
            `;
        }
        return lines;
    }

    attachEvents() {
        // Layer hover/click
        this.container.querySelectorAll('.iso-layer').forEach(layer => {
            layer.addEventListener('mouseenter', () => {
                const idx = parseInt(layer.dataset.layer);
                this.highlightLayer(idx);
            });
            layer.addEventListener('click', () => {
                const idx = parseInt(layer.dataset.layer);
                this.setActive(idx);
                this.dispatchEvent(idx);
            });
        });

        this.container.addEventListener('mouseleave', () => {
            this.highlightLayer(this.activeLayer);
        });
    }

    highlightLayer(index) {
        this.container.querySelectorAll('.iso-layer').forEach((layer, i) => {
            const isTarget = i === index;
            layer.style.opacity = isTarget ? '1' : '0.4';
            layer.style.transform = isTarget ? 'translateY(-5px)' : '';
            layer.style.filter = isTarget ? 'url(#glow)' : '';
        });

        this.container.querySelectorAll('.iso-side-label').forEach((label, i) => {
            label.setAttribute('opacity', i === index ? '1' : '0.3');
        });
    }

    setActive(index, animate = true) {
        this.activeLayer = index;
        
        this.container.querySelectorAll('.iso-layer').forEach((layer, i) => {
            const isActive = i === index;
            layer.classList.toggle('active', isActive);
            
            if (animate) {
                layer.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
            }
            
            // Expand/collapse effect
            const faces = layer.querySelectorAll('.iso-face');
            const highlight = layer.querySelector('.iso-highlight');
            
            if (isActive) {
                layer.style.opacity = '1';
                if (highlight) {
                    highlight.style.fillOpacity = '0.3';
                    highlight.style.strokeOpacity = '1';
                }
            } else {
                layer.style.opacity = '0.5';
                if (highlight) {
                    highlight.style.fillOpacity = '0';
                    highlight.style.strokeOpacity = '0';
                }
            }
        });

        this.container.querySelectorAll('.iso-side-label').forEach((label, i) => {
            label.setAttribute('opacity', i === index ? '1' : '0.3');
            label.style.fontWeight = i === index ? '600' : '400';
        });
    }

    dispatchEvent(index) {
        const event = new CustomEvent('layerchange', {
            detail: { 
                index, 
                layer: this.layers[index] 
            }
        });
        this.container.dispatchEvent(event);
    }

    // External API to set active layer
    selectLayer(index) {
        if (index >= 0 && index < this.layers.length) {
            this.setActive(index);
        }
    }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = IsometricLayers;
}