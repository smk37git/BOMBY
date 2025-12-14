/**
 * Isometric Layers
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
        
        this.w = 700;
        this.h = 300;
        this.t = 75;
        this.baseGap = -100;
        this.expandAmount = 100;
        this.offsetX = 175;
        this.startY = 0;
        this.svgW = 1020;
        this.svgH = 550;
        
        this.init();
    }

    init() {
        this.render();
        this.attachEvents();
        this.setActive(this.activeLayer, false);
    }

    getBaseY(index) {
        const layerHeight = this.h / 2 + this.t + this.baseGap;
        return this.startY + index * layerHeight;
    }

    // Gap opens between layer above active and active layer
    getTransformY(index, activeIndex) {
        if (activeIndex > 0 && index >= activeIndex) {
            return this.expandAmount;
        }
        return 0;
    }

    render() {
        const renderOrder = [3, 2, 1, 0];
        
        this.container.innerHTML = `
            <div class="iso-layers-wrapper">
                <svg class="iso-layers-svg" viewBox="0 0 ${this.svgW} ${this.svgH}" preserveAspectRatio="xMidYMin meet">
                    <g class="dots-grid" opacity="0.04">
                        ${this.renderDots()}
                    </g>
                    ${renderOrder.map(i => this.renderLayer(i)).join('')}
                </svg>
            </div>
        `;
    }

    renderDots() {
        let dots = '';
        for (let x = 15; x < this.svgW - 15; x += 20) {
            for (let y = 15; y < this.svgH - 15; y += 20) {
                dots += `<circle cx="${x}" cy="${y}" r="1" fill="white"/>`;
            }
        }
        return dots;
    }

    renderLayer(index) {
        const layer = this.layers[index];
        const y = this.getBaseY(index);
        const x = this.offsetX;
        const w = this.w, h = this.h, t = this.t;
        
        const topPath = `M ${x} ${y + h/2} L ${x + w/2} ${y} L ${x + w} ${y + h/2} L ${x + w/2} ${y + h} Z`;
        const leftPath = `M ${x} ${y + h/2} L ${x} ${y + h/2 + t} L ${x + w/2} ${y + h + t} L ${x + w/2} ${y + h} Z`;
        const rightPath = `M ${x + w} ${y + h/2} L ${x + w} ${y + h/2 + t} L ${x + w/2} ${y + h + t} L ${x + w/2} ${y + h} Z`;
        
        // Isometric transform for left face: x-axis follows slope, y-axis vertical
        const labelX = x + w/4;
        const labelY = y + h*0.75 + t/2;
        const angle = Math.atan(h / w); // radians
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);
        // matrix(a, b, c, d, e, f) = matrix(cosθ, sinθ, 0, 1, tx, ty)
        
        return `
            <g class="iso-layer" data-layer="${index}" transform="translate(0, 0)">
                <g class="iso-box">
                    <path class="iso-left" d="${leftPath}" fill="#080808" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <path class="iso-right" d="${rightPath}" fill="#0d0d0d" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>
                    <path class="iso-top" d="${topPath}" fill="#0a0a0a" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
                    <g class="iso-grid" opacity="0.15">${this.renderTopGrid(x, y, w, h, index)}</g>
                </g>
                <g class="iso-rings" opacity="0">${index === 0 ? '' : ''}</g>
                <text class="iso-layer-label" 
                      transform="matrix(${cos.toFixed(4)}, ${sin.toFixed(4)}, 0, 1, ${labelX}, ${labelY})"
                      text-anchor="middle"
                      dominant-baseline="middle"
                      fill="rgba(255,255,255,0.5)" font-size="18" font-weight="700"
                      font-family="system-ui, -apple-system, sans-serif">${layer.label}</text>
            </g>
        `;
    }

    renderTopGrid(x, y, w, h, index) {
        const cx = x + w/2;
        const cy = y + h/2;
        
        switch(index) {
            case 0: // Deployment - radial lines from center
                return this.renderRadialLines(x, y, w, h);
            
            case 1: // Setup - grid with dots
                return this.renderDottedGrid(x, y, w, h);
            
            case 2: // Extras - concentric diamonds
                return this.renderConcentricDiamonds(x, y, w, h);
            
            case 3: // AI Enhancements - neural network nodes
                return this.renderNeuralPattern(x, y, w, h);
            
            default:
                return this.renderDashedGrid(x, y, w, h);
        }
    }

    renderRadialLines(x, y, w, h) {
        let grid = '';
        const cx = x + w/2;
        const cy = y + h/2;
        
        // Main X
        grid += `<line x1="${x}" y1="${cy}" x2="${x + w}" y2="${cy}" stroke="white" stroke-width="0.6"/>`;
        grid += `<line x1="${cx}" y1="${y}" x2="${cx}" y2="${y + h}" stroke="white" stroke-width="0.6"/>`;
        
        // 3 chevrons per quadrant - nested from center outward
        for (let i = 1; i <= 3; i++) {
            const r = i * 0.25;
            
            // Top ^ - tip points up
            grid += `<path d="M ${cx - r*w/2} ${cy} L ${cx} ${cy - r*h/2} L ${cx + r*w/2} ${cy}" fill="none" stroke="white" stroke-width="0.5"/>`;
            
            // Bottom v - tip points down
            grid += `<path d="M ${cx - r*w/2} ${cy} L ${cx} ${cy + r*h/2} L ${cx + r*w/2} ${cy}" fill="none" stroke="white" stroke-width="0.5"/>`;
            
            // Left < - tip points left
            grid += `<path d="M ${cx} ${cy - r*h/2} L ${cx - r*w/2} ${cy} L ${cx} ${cy + r*h/2}" fill="none" stroke="white" stroke-width="0.5"/>`;
            
            // Right > - tip points right
            grid += `<path d="M ${cx} ${cy - r*h/2} L ${cx + r*w/2} ${cy} L ${cx} ${cy + r*h/2}" fill="none" stroke="white" stroke-width="0.5"/>`;
        }
        
        return grid;
    }

    renderNeuralPattern(x, y, w, h) {
        let grid = '';
        const cx = x + w/2;
        const cy = y + h/2;
        
        // Concentric pulsing rings with data points
        for (let i = 1; i <= 4; i++) {
            const r = i / 5;
            const rx = w/2 * r * 0.8;
            const ry = h/2 * r * 0.8;
            grid += `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="none" stroke="white" stroke-width="${i === 2 ? 1.5 : 0.5}"/>`;
        }
        
        // Orbiting dots on rings
        const dotCounts = [4, 6, 8, 10];
        dotCounts.forEach((count, ringIdx) => {
            const r = (ringIdx + 1) / 5;
            const rx = w/2 * r * 0.8;
            const ry = h/2 * r * 0.8;
            
            for (let i = 0; i < count; i++) {
                const angle = (i / count) * Math.PI * 2 + ringIdx * 0.3;
                const dotX = cx + Math.cos(angle) * rx;
                const dotY = cy + Math.sin(angle) * ry;
                grid += `<circle cx="${dotX}" cy="${dotY}" r="3" fill="white"/>`;
            }
        });
        
        // Center dot
        grid += `<circle cx="${cx}" cy="${cy}" r="5" fill="white"/>`;
        
        return grid;
    }

    renderDashedGrid(x, y, w, h) {
        let grid = '';
        const steps = 5;
        for (let i = 1; i < steps; i++) {
            const r = i / steps;
            grid += `<line x1="${x + r*w/2}" y1="${y + h/2 - r*h/2}" x2="${x + w/2 + r*w/2}" y2="${y + h - r*h/2}" stroke="white" stroke-width="0.5" stroke-dasharray="4,4"/>`;
            grid += `<line x1="${x + r*w/2}" y1="${y + h/2 + r*h/2}" x2="${x + w/2 + r*w/2}" y2="${y + r*h/2}" stroke="white" stroke-width="0.5" stroke-dasharray="4,4"/>`;
        }
        return grid;
    }

    renderDottedGrid(x, y, w, h) {
        let grid = '';
        const steps = 6;
        // Grid lines
        for (let i = 1; i < steps; i++) {
            const r = i / steps;
            grid += `<line x1="${x + r*w/2}" y1="${y + h/2 - r*h/2}" x2="${x + w/2 + r*w/2}" y2="${y + h - r*h/2}" stroke="white" stroke-width="0.5"/>`;
            grid += `<line x1="${x + r*w/2}" y1="${y + h/2 + r*h/2}" x2="${x + w/2 + r*w/2}" y2="${y + r*h/2}" stroke="white" stroke-width="0.5"/>`;
        }
        // Dots at intersections
        for (let i = 1; i < steps; i++) {
            for (let j = 1; j < steps; j++) {
                const px = x + (i/steps)*w/2 + (j/steps)*w/2;
                const py = y + h/2 - (i/steps)*h/2 + (j/steps)*h/2;
                grid += `<circle cx="${px}" cy="${py}" r="2.5" fill="white"/>`;
            }
        }
        return grid;
    }

    renderConcentricDiamonds(x, y, w, h) {
        let grid = '';
        const cx = x + w/2;
        const cy = y + h/2;
        const steps = 6;
        
        for (let i = 1; i <= steps; i++) {
            const r = i / steps;
            const rx = r * w/2 * 0.85;
            const ry = r * h/2 * 0.85;
            grid += `<path d="M ${cx} ${cy - ry} L ${cx + rx} ${cy} L ${cx} ${cy + ry} L ${cx - rx} ${cy} Z" 
                     fill="none" stroke="white" stroke-width="0.5" stroke-dasharray="${i === steps ? '0' : '2,3'}"/>`;
        }
        return grid;
    }

    renderRings(cx, cy, rx, ry) {
        return `
            <ellipse cx="${cx}" cy="${cy}" rx="${rx*2.5}" ry="${ry*1.25}" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4,6"/>
            <ellipse cx="${cx}" cy="${cy}" rx="${rx*1.5}" ry="${ry*0.75}" fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="1"/>
            <ellipse cx="${cx}" cy="${cy}" rx="${rx*0.6}" ry="${ry*0.3}" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="1.5"/>
        `;
    }

    renderSideLabel(index) {
        const layer = this.layers[index];
        const y = this.getBaseY(index);
        const lineY = y + this.h/2 + this.t/2;
        const labelX = 730;
        
        return `
            <g class="iso-side-label-group" data-layer="${index}" transform="translate(0, 0)">
                <line class="iso-connection" x1="${this.offsetX + this.w + 10}" y1="${lineY}" x2="${labelX - 5}" y2="${lineY}"
                      stroke="rgba(255,255,255,0.05)" stroke-width="1" stroke-dasharray="2,5"/>
                <text class="iso-side-label" x="${labelX}" y="${lineY + 4}" text-anchor="start"
                      fill="rgba(255,255,255,0.1)" font-size="10" letter-spacing="2px" font-family="system-ui, sans-serif">${layer.sideLabel}</text>
            </g>
        `;
    }

    attachEvents() {
        this.container.querySelectorAll('.iso-layer').forEach(layer => {
            layer.addEventListener('mouseenter', () => this.highlightLayer(parseInt(layer.dataset.layer)));
            layer.addEventListener('click', () => {
                const idx = parseInt(layer.dataset.layer);
                this.setActive(idx);
                this.dispatchEvent(idx);
            });
        });
        this.container.addEventListener('mouseleave', () => this.highlightLayer(this.activeLayer));
    }

    highlightLayer(index) {
        this.container.querySelectorAll('.iso-layer').forEach((layer) => {
            const idx = parseInt(layer.dataset.layer);
            const top = layer.querySelector('.iso-top');
            const left = layer.querySelector('.iso-left');
            const right = layer.querySelector('.iso-right');
            const label = layer.querySelector('.iso-layer-label');
            
            if (idx === index) {
                top.setAttribute('stroke', 'rgba(255,255,255,0.45)');
                left.setAttribute('stroke', 'rgba(255,255,255,0.45)');
                right.setAttribute('stroke', 'rgba(255,255,255,0.45)');
                label.setAttribute('fill', 'rgba(255,255,255,0.65)');
            } else if (idx === this.activeLayer) {
                top.setAttribute('stroke', 'rgba(255,255,255,0.6)');
                left.setAttribute('stroke', 'rgba(255,255,255,0.6)');
                right.setAttribute('stroke', 'rgba(255,255,255,0.6)');
                label.setAttribute('fill', 'rgba(255,255,255,0.95)');
            } else {
                top.setAttribute('stroke', 'rgba(255,255,255,0.1)');
                left.setAttribute('stroke', 'rgba(255,255,255,0.05)');
                right.setAttribute('stroke', 'rgba(255,255,255,0.05)');
                label.setAttribute('fill', 'rgba(255,255,255,0.22)');
            }
        });
    }

    setActive(index, animate = true) {
        this.activeLayer = index;
        
        this.container.querySelectorAll('.iso-layer').forEach((layer) => {
            const idx = parseInt(layer.dataset.layer);
            const transformY = this.getTransformY(idx, index);
            
            layer.style.transition = animate ? 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)' : 'none';
            layer.setAttribute('transform', `translate(0, ${transformY})`);
            
            this.applyLayerStyles(layer, idx === index);
        });

        this.container.querySelectorAll('.iso-side-label-group').forEach((g) => {
            const idx = parseInt(g.dataset.layer);
            const transformY = this.getTransformY(idx, index);
            
            g.style.transition = animate ? 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)' : 'none';
            g.setAttribute('transform', `translate(0, ${transformY})`);
            
            g.querySelector('.iso-side-label').setAttribute('fill', idx === index ? 'rgba(255,255,255,0.8)' : 'rgba(255,255,255,0.1)');
            g.querySelector('.iso-connection').setAttribute('stroke', idx === index ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.05)');
        });
    }

    // Highlight layer visually without moving
    highlightActive(index) {
        this.activeLayer = index;
        this.container.querySelectorAll('.iso-layer').forEach((layer) => {
            const idx = parseInt(layer.dataset.layer);
            this.applyLayerStyles(layer, idx === index);
        });
    }

    // Move layers to their positions for active index
    moveToActive(index) {
        this.container.querySelectorAll('.iso-layer').forEach((layer) => {
            const idx = parseInt(layer.dataset.layer);
            const transformY = this.getTransformY(idx, index);
            layer.style.transition = 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)';
            layer.setAttribute('transform', `translate(0, ${transformY})`);
        });
    }

    applyLayerStyles(layer, isActive) {
        const rings = layer.querySelector('.iso-rings');
        const label = layer.querySelector('.iso-layer-label');
        const top = layer.querySelector('.iso-top');
        const left = layer.querySelector('.iso-left');
        const right = layer.querySelector('.iso-right');
        const grid = layer.querySelector('.iso-grid');
        
        rings.style.transition = 'opacity 0.5s ease';
        rings.style.opacity = isActive ? '1' : '0';
        
        if (isActive) {
            label.setAttribute('fill', 'rgba(255,255,255,1)');
            top.setAttribute('stroke', 'rgba(255,255,255,0.6)');
            top.setAttribute('stroke-width', '1.5');
            left.setAttribute('stroke', 'rgba(255,255,255,0.6)');
            left.setAttribute('stroke-width', '1.5');
            right.setAttribute('stroke', 'rgba(255,255,255,0.6)');
            right.setAttribute('stroke-width', '1.5');
            grid.setAttribute('opacity', '0.25');
        } else {
            label.setAttribute('fill', 'rgba(255,255,255,0.25)');
            top.setAttribute('stroke', 'rgba(255,255,255,0.1)');
            top.setAttribute('stroke-width', '1');
            left.setAttribute('stroke', 'rgba(255,255,255,0.05)');
            left.setAttribute('stroke-width', '1');
            right.setAttribute('stroke', 'rgba(255,255,255,0.05)');
            right.setAttribute('stroke-width', '1');
            grid.setAttribute('opacity', '0.12');
        }
    }

    dispatchEvent(index) {
        this.container.dispatchEvent(new CustomEvent('layerchange', { detail: { index, layer: this.layers[index] } }));
    }

    selectLayer(index) {
        if (index >= 0 && index < this.layers.length) this.setActive(index);
    }
}

if (typeof module !== 'undefined' && module.exports) module.exports = IsometricLayers;