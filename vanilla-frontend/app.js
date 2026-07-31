document.addEventListener('DOMContentLoaded', () => {

    // --- DEMO MODE INJECTION ---
    const DEMO_STOCKS = [
        { symbol: 'RELIANCE', label: 'Reliance Industries', sector: 'Energy' },
        { symbol: 'TCS', label: 'Tata Consultancy', sector: 'Technology' },
        { symbol: 'ZOMATO', label: 'Zomato', sector: 'Consumer' },
        { symbol: 'ADANIPORTS', label: 'Adani Ports', sector: 'Infrastructure' },
        { symbol: 'IRFC', label: 'IRFC', sector: 'Finance' }
    ];
    const demoCache = {};

    let activeDemoSymbol = null;

    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');
    const watchlist = document.getElementById('watchlist');
    const demoStocksEl = document.getElementById('demoStocks');

    function setActiveDemoStockRow(symbol) {
        if (!demoStocksEl) {
            activeDemoSymbol = symbol;
            return;
        }
        const rows = demoStocksEl.querySelectorAll('.demo-stock-row');
        rows.forEach((row) => {
            if (row.dataset.symbol === symbol) {
                row.classList.add('active');
            } else {
                row.classList.remove('active');
            }
        });
        activeDemoSymbol = symbol;
    }

    function renderDemoStockRows() {
        if (!demoStocksEl) return;

        demoStocksEl.innerHTML = DEMO_STOCKS.map((stock) => `
            <div class="demo-stock-row${activeDemoSymbol === stock.symbol ? ' active' : ''}" data-symbol="${stock.symbol}" onclick="loadStock('${stock.symbol}')">
                <span class="demo-symbol">${stock.symbol}</span>
                <span class="demo-sector">${stock.sector}</span>
            </div>
        `).join('');
    }

    function getStockBySymbol(symbol) {
        return DEMO_STOCKS.find((stock) => stock.symbol === symbol.toUpperCase().trim()) || null;
    }

    function loadStock(symbol) {
        const stock = getStockBySymbol(symbol);
        if (!stock) return;
        selectStock(stock);
    }

    window.loadStock = loadStock;

    function prefetchDemoStocks() {
        return Promise.all(DEMO_STOCKS.map((s) =>
            fetch(`/api/stock/${s.symbol}/snapshot`)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null)
        )).then((results) => {
            results.forEach((data, i) => {
                demoCache[DEMO_STOCKS[i].symbol] = data;
            });
        });
    }

    renderDemoStockRows();
    prefetchDemoStocks().finally(() => {
        loadStock('RELIANCE');
    });
    // ----------------------------
    
    // Top strip elements
    const stockSymbolEl = document.getElementById('stockSymbol');
    const stockPriceEl = document.getElementById('stockPrice');
    const stockChangeEl = document.getElementById('stockChange');
    const priceMarkerEl = document.getElementById('priceMarker');
    const deliveryTextEl = document.getElementById('deliveryText');
    const deliveryFillEl = document.getElementById('deliveryFill');
    
    // Tab 1 Elements
    const promoterCanvas = document.getElementById('promoterCanvas');
    const velocityScoreEl = document.getElementById('velocityScore');
    const velocityMarkerEl = document.getElementById('velocityMarker');
    const velocityScoreWrapperEl = document.getElementById('velocityScoreWrapper');
    const promoterTextEl = document.getElementById('promoterText');

    // Tab 2 Elements
    const expiryCanvas = document.getElementById('expiryCanvas');
    const patternLabelEl = document.getElementById('patternLabel');
    const confidenceTicksEl = document.getElementById('confidenceTicks');
    const confidenceTextEl = document.getElementById('confidenceText');
    const expiryTextEl = document.getElementById('expiryText');

    // Tab 3 Elements
    const riskScoreValueEl = document.getElementById('riskScoreValue');
    const riskScoreVerdictEl = document.getElementById('riskScoreVerdict');
    const filingsTimelineEl = document.getElementById('filingsTimeline');
    
    // Corporate Actions Elements
    const timelineCanvas = document.getElementById('timelineCanvas');
    const shareholdingCanvas = document.getElementById('shareholdingCanvas');
    const timelineTooltip = document.getElementById('timelineTooltip');

    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    let debounceTimer;

    // Search input handler
    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const query = e.target.value.trim();
        
        if (query.length < 2) {
            searchResults.innerHTML = '';
            return;
        }

        debounceTimer = setTimeout(() => {
            fetchSearchResults(query);
        }, 300);
    });

    async function fetchSearchResults(query) {
        try {
            // Mock API call
            const mockData = [
                { symbol: 'RELIANCE', name: 'Reliance Industries Ltd' },
                { symbol: 'TCS', name: 'Tata Consultancy Services' },
                { symbol: 'HDFCBANK', name: 'HDFC Bank Ltd' }
            ].filter(s => s.symbol.toLowerCase().includes(query.toLowerCase()) || s.name.toLowerCase().includes(query.toLowerCase()));

            renderSearchResults(mockData);
        } catch (error) {
            console.error('Error fetching search results:', error);
        }
    }

    function renderSearchResults(results) {
        searchResults.innerHTML = '';
        results.forEach(stock => {
            const li = document.createElement('li');
            li.className = 'search-result-item';
            li.innerHTML = `
                <span class="number-font">${stock.symbol}</span>
                <span class="text-muted" style="font-size: 12px; margin-left: 8px;">${stock.name}</span>
            `;
            li.addEventListener('click', () => {
                selectStock(stock);
                searchInput.value = '';
                searchResults.innerHTML = '';
            });
            searchResults.appendChild(li);
        });
    }

    function selectStock(stock) {
        const stockTitle = stock.label || stock.name || stock.symbol;
        const snapshotPayload = demoCache[stock.symbol];
        const snapshot = snapshotPayload && typeof snapshotPayload === 'object' && snapshotPayload.snapshot
            ? snapshotPayload.snapshot
            : snapshotPayload;
        const quote = snapshot && typeof snapshot === 'object' ? snapshot.quote : null;

        // Update top bar
        stockSymbolEl.textContent = stockTitle;

        // Prefer pre-fetched snapshot values when available.
        const hasQuote = quote && typeof quote === 'object' && typeof quote.price === 'number';
        const basePrice = hasQuote ? quote.price : (Math.random() * 3000 + 500);
        const changeAbs = hasQuote && typeof quote.change === 'number'
            ? quote.change
            : ((Math.random() * 40) - 20);
        const changePct = hasQuote && typeof quote.percent_change === 'number'
            ? quote.percent_change
            : ((changeAbs / basePrice) * 100);
        const currentPrice = basePrice;
        
        stockPriceEl.textContent = currentPrice.toFixed(2);
        
        const sign = changeAbs > 0 ? '+' : '';
        stockChangeEl.textContent = `${sign}${changeAbs.toFixed(2)} (${sign}${changePct.toFixed(2)}%)`;
        
        if (changeAbs >= 0) {
            stockPriceEl.classList.remove('negative');
            stockPriceEl.classList.add('positive');
            stockChangeEl.classList.remove('negative');
            stockChangeEl.classList.add('positive');
        } else {
            stockPriceEl.classList.remove('positive');
            stockPriceEl.classList.add('negative');
            stockChangeEl.classList.remove('positive');
            stockChangeEl.classList.add('negative');
        }

        // 52-week range positioning (use quote when available).
        let rangePos = Math.random() * 100;
        if (
            hasQuote &&
            typeof quote.fifty_two_week_low === 'number' &&
            typeof quote.fifty_two_week_high === 'number' &&
            quote.fifty_two_week_high > quote.fifty_two_week_low
        ) {
            rangePos = ((currentPrice - quote.fifty_two_week_low) / (quote.fifty_two_week_high - quote.fifty_two_week_low)) * 100;
            rangePos = Math.max(0, Math.min(100, rangePos));
        }
        priceMarkerEl.style.left = `${rangePos}%`;

        // Delivery (fallback to mock if unavailable).
        const deliveryPct = snapshot && snapshot.basic_metrics && typeof snapshot.basic_metrics.delivery_percent === 'number'
            ? Math.round(snapshot.basic_metrics.delivery_percent)
            : Math.floor(Math.random() * 40 + 20);
        deliveryTextEl.textContent = `${deliveryPct}%`;
        deliveryFillEl.style.height = `${deliveryPct}%`;

        setActiveDemoStockRow(stock.symbol);

        // Add to "watchlist" / selector area
        updateSelectorArea(stock);
        
        // Render Tabs
        renderPromoterVelocity(stock);
        renderExpiryPattern(stock);
        renderFilingRedFlags(stock);
        renderCorporateActions(stock);
    }
    
    function renderPromoterVelocity(stock) {
        // Resize canvas to actual container width
        const ctx = promoterCanvas.getContext('2d');
        const width = promoterCanvas.parentElement.clientWidth || 800;
        const height = promoterCanvas.height;
        
        promoterCanvas.width = width;
        
        // Mock Data
        const quarters = ["Q1 FY22", "Q2 FY22", "Q3 FY22", "Q4 FY22", "Q1 FY23", "Q2 FY23", "Q3 FY23", "Q4 FY23"];
        // Random walk
        let holdings = [45.0];
        for(let i=1; i<8; i++) holdings.push(holdings[i-1] + (Math.random() * 2 - 0.8));
        
        const minVal = Math.min(...holdings);
        const maxVal = Math.max(...holdings);
        const padding = (maxVal - minVal) * 0.05 || 1;
        const lowerBound = minVal - padding;
        const upperBound = maxVal + padding;
        
        ctx.clearRect(0, 0, width, height);
        
        const isNegative = holdings[holdings.length-1] < holdings[0];
        const strokeColor = isNegative ? '#ff4444' : '#c8ff00';
        
        const marginX = 40;
        const marginY = 20;
        const graphWidth = width - marginX * 2;
        const graphHeight = height - marginY * 2;
        
        // Draw path
        ctx.beginPath();
        holdings.forEach((v, i) => {
            const x = marginX + (i / 7) * graphWidth;
            const y = height - marginY - ((v - lowerBound) / (upperBound - lowerBound)) * graphHeight;
            if(i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        
        // Draw Points & Labels
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.font = "10px 'JetBrains Mono'";
        ctx.fillStyle = "#666";
        
        holdings.forEach((v, i) => {
            const x = marginX + (i / 7) * graphWidth;
            const y = height - marginY - ((v - lowerBound) / (upperBound - lowerBound)) * graphHeight;
            
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, 2 * Math.PI);
            ctx.fillStyle = strokeColor;
            ctx.fill();
            
            // Draw x-axis label
            ctx.fillStyle = "#666";
            ctx.fillText(quarters[i], x, height - 15);
        });
        
        // Gauge
        const cached = demoCache[stock.symbol];
        const score = cached?.promoter?.velocity !== undefined ? Math.round(cached.promoter.velocity) : Math.floor(Math.random() * 200 - 100);
        velocityScoreEl.textContent = score;
        
        let color = "#fff";
        if(score > 0) color = "#c8ff00";
        if(score < 0) color = "#ff4444";
        velocityScoreEl.style.color = color;
        velocityMarkerEl.style.backgroundColor = color;
        
        const pct = ((score + 100) / 200) * 100;
        velocityMarkerEl.style.left = `${pct}%`;
        velocityScoreWrapperEl.style.left = `${pct}%`;
        
        promoterTextEl.textContent = `Promoters have been ${score >= 0 ? 'buying' : 'selling'} at an ${Math.abs(score) > 50 ? 'accelerating' : 'decelerating'} rate over the last 8 quarters. Historical correlation with 30-day forward returns: ${Math.floor(Math.random()*40 + 20)}%.`;
    }

    function renderExpiryPattern(stock) {
        const ctx = expiryCanvas.getContext('2d');
        const width = expiryCanvas.parentElement.clientWidth || 800;
        const height = expiryCanvas.height;
        expiryCanvas.width = width;
        
        ctx.clearRect(0, 0, width, height);
        
        const marginX = 40;
        const marginY = 20;
        const graphWidth = width - marginX * 2;
        const graphHeight = height - marginY * 2;
        
        // Zero return line
        const midY = marginY + graphHeight / 2;
        ctx.beginPath();
        ctx.moveTo(marginX, midY);
        ctx.lineTo(width - marginX, midY);
        ctx.strokeStyle = "#333";
        ctx.lineWidth = 1;
        ctx.stroke();
        
        // Vertical dashed line (x=0)
        const zeroX = marginX + (5 / 10) * graphWidth;
        ctx.beginPath();
        ctx.setLineDash([4, 4]);
        ctx.moveTo(zeroX, marginY);
        ctx.lineTo(zeroX, height - marginY);
        ctx.strokeStyle = "#333";
        ctx.stroke();
        ctx.setLineDash([]);
        
        // Axis Labels
        ctx.font = "10px 'JetBrains Mono'";
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        
        for(let i = -5; i <= 5; i++) {
            const x = marginX + ((i + 5) / 10) * graphWidth;
            ctx.fillText(i.toString(), x, height - 15);
        }
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        ctx.fillText("+5%", marginX - 5, marginY);
        ctx.fillText("-5%", marginX - 5, height - marginY);
        
        // Dots
        const colors = ["#c8ff00", "#4488ff", "#ff8844", "#ff4444", "#aa44ff", "#44ffcc"];
        for(let expiry = 0; expiry < 12; expiry++) {
            const color = colors[expiry % colors.length];
            for(let day = -5; day <= 5; day++) {
                const x = marginX + ((day + 5) / 10) * graphWidth;
                const ret = (Math.random() * 10 - 5);
                const y = marginY + graphHeight / 2 - (ret / 5) * (graphHeight / 2);
                
                const jitter = (Math.random() * 4) - 2;
                
                ctx.beginPath();
                ctx.arc(x, y + jitter, 5, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
            }
        }
        
        // Detection Logic
        const patterns = ["Expiry Rally", "Pre-Expiry Dump", "Range-bound Chop", "Volatile Whip"];
        patternLabelEl.textContent = demoCache[stock.symbol]?.expiry?.pattern || patterns[Math.floor(Math.random() * patterns.length)];
        
        const cached = demoCache[stock.symbol];
        const confStr = cached?.expiry?.current_signal?.pattern_confidence;
        const conf = confStr ? Math.round(parseFloat(confStr)) : Math.floor(Math.random() * 40 + 50);
        confidenceTextEl.textContent = `${conf}%`;
        
        const filledTicks = Math.round((conf / 100) * 10);
        confidenceTicksEl.innerHTML = '';
        for(let i=0; i<10; i++) {
            const t = document.createElement('div');
            t.className = 'tick' + (i < filledTicks ? ' filled' : '');
            confidenceTicksEl.appendChild(t);
        }
        
        const today = new Date();
        const dStr = today.toLocaleDateString('en-GB', {weekday: 'long', day: 'numeric', month: 'short', year: 'numeric'});
        expiryTextEl.textContent = `3 days to next expiry (${dStr}). Based on detected pattern, expect increased intraday volatility with an upward bias into the last hour.`;
    }

    function renderFilingRedFlags(stock) {
        const cached = demoCache[stock.symbol];
        const score = cached?.filings?.risk_score !== undefined ? Math.round(parseFloat(cached.filings.risk_score)) : Math.floor(Math.random() * 100);
        riskScoreValueEl.textContent = score;
        
        if (score < 30) {
            riskScoreValueEl.style.color = '#c8ff00';
            riskScoreVerdictEl.textContent = "No significant red flags detected in recent filings.";
        } else if (score <= 60) {
            riskScoreValueEl.style.color = '#ffaa00';
            riskScoreVerdictEl.textContent = "Some filings warrant attention. Review flagged items below.";
        } else {
            riskScoreValueEl.style.color = '#ff4444';
            riskScoreVerdictEl.textContent = "Multiple high-risk signals detected. Proceed with caution.";
        }
        
        filingsTimelineEl.innerHTML = '';
        
        const flags = [
            { date: "10 Apr 2024", title: "Change in Key Managerial Personnel (CFO Resignation)", type: "amber", label: "director change" },
            { date: "02 Apr 2024", title: "Disclosure under Reg 29(2) - Promoter Share Pledge", type: "red", label: "promoter pledge" },
            { date: "15 Mar 2024", title: "Intimation of Board Meeting for Q4 Results", type: "lime", label: null }
        ];
        
        flags.forEach(f => {
            const row = document.createElement('div');
            row.className = 'filing-row';
            
            const colorCode = f.type === 'lime' ? '#c8ff00' : (f.type === 'amber' ? '#ffaa00' : '#ff4444');
            
            let labelHtml = f.label ? `<span class="filing-flag" style="color: ${colorCode}">${f.label}</span>` : '';
            
            row.innerHTML = `
                <div class="filing-dot" style="background-color: ${colorCode};"></div>
                <div class="filing-connector"></div>
                <div class="filing-date">${f.date}</div>
                <div class="filing-headline">${f.title}</div>
                ${labelHtml}
                <div class="filing-expanded">
                    <div class="expanded-content">
                        <strong>${f.title}</strong><br><br>
                        "The Board of Directors have received and accepted the resignation of Mr. John Doe from the post of CFO, effective immediately due to personal reasons..."
                        <br>
                        <a href="#" class="bse-link" target="_blank">view on BSE</a>
                    </div>
                </div>
            `;
            
            row.addEventListener('click', () => {
                row.classList.toggle('open');
            });
            
            filingsTimelineEl.appendChild(row);
        });
    }

    function renderCorporateActions(stock) {
        // --- Timeline & Price Area ---
        const tCtx = timelineCanvas.getContext('2d');
        const tWidth = timelineCanvas.parentElement.clientWidth || 800;
        const tHeight = timelineCanvas.height;
        timelineCanvas.width = tWidth;
        
        tCtx.clearRect(0, 0, tWidth, tHeight);
        
        // Mock Price Data
        const pricePoints = 100;
        const prices = [];
        let p = 100;
        for(let i=0; i<pricePoints; i++) {
            prices.push(p);
            p += (Math.random() * 6 - 2.5); // drift upwards slightly
        }
        const minP = Math.min(...prices);
        const maxP = Math.max(...prices);
        
        // Draw Area Fill for Price
        tCtx.beginPath();
        tCtx.moveTo(0, tHeight);
        for(let i=0; i<pricePoints; i++) {
            const x = (i / (pricePoints - 1)) * tWidth;
            const y = tHeight - ((prices[i] - minP) / (maxP - minP)) * tHeight * 0.8;
            tCtx.lineTo(x, y);
        }
        tCtx.lineTo(tWidth, tHeight);
        tCtx.fillStyle = 'rgba(255, 255, 255, 0.03)';
        tCtx.fill();
        
        // Timeline axis
        const axisY = tHeight - 15;
        tCtx.beginPath();
        tCtx.moveTo(0, axisY);
        tCtx.lineTo(tWidth, axisY);
        tCtx.strokeStyle = '#333';
        tCtx.lineWidth = 1;
        tCtx.stroke();
        
        // Mock Events
        const events = [
            { type: 'dividend', date: 'Jul 2023', val: '₹15/sh', ratio: 0.2 },
            { type: 'bonus', date: 'Oct 2023', val: '1:1', ratio: 0.5 },
            { type: 'dividend', date: 'Jan 2024', val: '₹5/sh', ratio: 0.7 },
            { type: 'rights', date: 'Mar 2024', val: '1:10', ratio: 0.9 }
        ];
        
        const hitRegions = [];
        
        events.forEach(ev => {
            const x = ev.ratio * tWidth;
            const y = axisY;
            tCtx.beginPath();
            if (ev.type === 'dividend') {
                // Downward triangle
                tCtx.moveTo(x - 5, y - 6);
                tCtx.lineTo(x + 5, y - 6);
                tCtx.lineTo(x, y + 2);
                tCtx.fillStyle = '#c8ff00';
            } else if (ev.type === 'bonus') {
                // Circle
                tCtx.arc(x, y - 3, 4, 0, Math.PI * 2);
                tCtx.fillStyle = '#ffffff';
            } else if (ev.type === 'rights') {
                // Upward triangle
                tCtx.moveTo(x, y - 8);
                tCtx.lineTo(x - 5, y);
                tCtx.lineTo(x + 5, y);
                tCtx.fillStyle = '#ffaa00';
            }
            tCtx.fill();
            
            // Year ticks
            tCtx.fillStyle = '#666';
            tCtx.font = "9px 'JetBrains Mono'";
            tCtx.textAlign = 'center';
            tCtx.fillText(ev.date, x, y + 12);
            
            hitRegions.push({ x, y: y-6, r: 8, ev });
        });
        
        // Hover logic for timeline
        timelineCanvas.onmousemove = (e) => {
            const rect = timelineCanvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            let hovered = null;
            hitRegions.forEach(hr => {
                const dist = Math.sqrt((mouseX - hr.x)**2 + (mouseY - hr.y)**2);
                if (dist < hr.r + 5) hovered = hr.ev;
            });
            
            if (hovered) {
                timelineTooltip.style.display = 'block';
                timelineTooltip.style.left = `${mouseX + 10}px`;
                timelineTooltip.style.top = `${mouseY - 20}px`;
                const typeName = hovered.type.charAt(0).toUpperCase() + hovered.type.slice(1);
                timelineTooltip.textContent = `${typeName} | ${hovered.date} | ${hovered.val}`;
            } else {
                timelineTooltip.style.display = 'none';
            }
        };
        timelineCanvas.onmouseleave = () => timelineTooltip.style.display = 'none';
        
        // --- Shareholding Stacked Bar Chart ---
        const sCtx = shareholdingCanvas.getContext('2d');
        const sWidth = shareholdingCanvas.parentElement.clientWidth || 800;
        const sHeight = shareholdingCanvas.height;
        shareholdingCanvas.width = sWidth;
        
        sCtx.clearRect(0, 0, sWidth, sHeight);
        
        const quarters = ["Q4 FY24", "Q3 FY24", "Q2 FY24", "Q1 FY24"];
        const rowHeight = sHeight / quarters.length;
        const barHeight = rowHeight * 0.6;
        
        // Base holdings
        let promoter = 45;
        let fii = 20;
        let dii = 15;
        let retail = 15;
        let other = 5;
        
        const shData = [];
        
        for(let i=0; i<quarters.length; i++) {
            shData.push([
                { name: "Promoter", val: promoter, color: "#c8ff00" },
                { name: "FII", val: fii, color: "#4488ff" },
                { name: "DII", val: dii, color: "#ff8844" },
                { name: "Retail", val: retail, color: "#666666" },
                { name: "Other", val: other, color: "#333333" }
            ]);
            // Vary slightly backwards in time
            promoter -= (Math.random() * 1 - 0.5);
            fii -= (Math.random() * 1 - 0.5);
            dii -= (Math.random() * 1 - 0.5);
            retail = 100 - promoter - fii - dii - other;
        }
        
        const shHitRegions = [];
        
        shData.forEach((qData, i) => {
            const y = i * rowHeight + (rowHeight - barHeight) / 2;
            
            // Draw Label
            sCtx.fillStyle = '#999';
            sCtx.font = "11px 'JetBrains Mono'";
            sCtx.textAlign = 'left';
            sCtx.textBaseline = 'middle';
            sCtx.fillText(quarters[i], 0, y + barHeight/2);
            
            let xOffset = 60;
            const availableW = sWidth - xOffset;
            
            qData.forEach(segment => {
                const w = (segment.val / 100) * availableW;
                sCtx.fillStyle = segment.color;
                sCtx.fillRect(xOffset, y, w, barHeight);
                
                shHitRegions.push({
                    x: xOffset, y: y, w: w, h: barHeight,
                    segment: segment, q: quarters[i]
                });
                
                // Gap between segments
                xOffset += w;
            });
        });
        
        // Shareholding Hover logic using timeline tooltip reused
        shareholdingCanvas.onmousemove = (e) => {
            const rect = shareholdingCanvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            
            let hovered = null;
            shHitRegions.forEach(hr => {
                if(mouseX >= hr.x && mouseX <= hr.x + hr.w && mouseY >= hr.y && mouseY <= hr.y + hr.h) {
                    hovered = hr.segment;
                }
            });
            
            if (hovered) {
                timelineTooltip.style.display = 'block';
                timelineTooltip.style.left = `${mouseX + 10}px`;
                timelineTooltip.style.top = `${mouseY + Math.floor(barHeight)}px`;
                timelineTooltip.textContent = `${hovered.name}: ${hovered.val.toFixed(2)}%`;
                
                // Switch parent for clean absolute positioning
                if (timelineTooltip.parentElement.className !== 'shareholding-wrapper') {
                    timelineTooltip.parentNode.removeChild(timelineTooltip);
                    shareholdingCanvas.parentElement.appendChild(timelineTooltip);
                }
            } else {
                timelineTooltip.style.display = 'none';
            }
        };
        shareholdingCanvas.onmouseleave = () => timelineTooltip.style.display = 'none';
        
        timelineCanvas.onmouseenter = () => {
            if (timelineTooltip.parentElement.className !== 'timeline-wrapper') {
                timelineTooltip.parentNode.removeChild(timelineTooltip);
                timelineCanvas.parentElement.appendChild(timelineTooltip);
            }
        };
    }

    function updateSelectorArea(stock) {
        // Clear previous selected state
        const items = watchlist.querySelectorAll('.watchlist-item');
        items.forEach(item => item.classList.remove('selected'));

        // Check if exists
        let existingItem = Array.from(items).find(item => item.dataset.symbol === stock.symbol);
        
        if (!existingItem) {
            existingItem = document.createElement('div');
            existingItem.className = 'watchlist-item selected';
            existingItem.dataset.symbol = stock.symbol;
            existingItem.innerHTML = `
                <div class="number-font" style="font-weight: 700; font-size: 16px; margin-bottom: 4px;">${stock.symbol}</div>
                <div class="text-muted" style="font-size: 12px;">${stock.label || stock.name || stock.symbol}</div>
            `;
            existingItem.addEventListener('click', () => selectStock(stock));
            watchlist.prepend(existingItem);
        } else {
            existingItem.classList.add('selected');
        }
    }

    // Tabs handler
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.tab;
            
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(targetTab).classList.add('active');
        });
    });

    // --- COMPOSITE VIEW LOGIC ---
    const compositeViewBtn = document.getElementById('compositeViewBtn');
    const compositeView = document.getElementById('compositeView');
    const compositeGrid = document.getElementById('compositeGrid');
    const highestSignal = document.getElementById('highestSignal');
    
    let isCompositeVisible = false;
    
    compositeViewBtn.addEventListener('click', () => {
        isCompositeVisible = !isCompositeVisible;
        
        if (isCompositeVisible) {
            compositeViewBtn.textContent = 'Close View';
            compositeView.style.display = 'flex';
            renderCompositeView();
        } else {
            compositeViewBtn.textContent = 'Composite View';
            compositeView.style.display = 'none';
        }
    });
    
    function parseValue(val) {
        if (val === undefined || val === null) return Math.floor(Math.random() * 100);
        return parseFloat(val);
    }
    
    function getBgColor(score) {
        if (score > 70) return 'rgba(200, 255, 0, 0.15)'; // Lime tint
        if (score < 30) return 'rgba(255, 68, 68, 0.15)'; // Red tint
        return 'transparent';
    }
    
    function renderCompositeView() {
        const dimensions = ['Promoter Velocity', 'Expiry Pattern', 'Filing Risk', 'OI Buildup', 'Corp Action Window'];
        
        let html = '';
        
        // Header Row
        html += `<div></div>`; // Empty top-left
        dimensions.forEach(dim => {
            html += `<div style="color: #666; font-size: 10px; text-transform: uppercase; padding-bottom: 10px; align-self: end;">${dim}</div>`;
        });
        
        let bestSignal = null;
        
        DEMO_STOCKS.forEach(stock => {
            const s = stock.symbol;
            const cached = demoCache[s] || {};
            
            // Calc scores 0-100
            // Promoter: velocity is generally -100 to 100. Normalize to 0-100. 
            const rawPromoter = parseValue(cached?.promoter?.velocity);
            const promoterScore = Math.max(0, Math.min(100, Math.round((rawPromoter + 100) / 2)));
            
            // Expiry: confidence is already roughly 0-100.
            const expiryScore = Math.round(parseValue(cached?.expiry?.current_signal?.pattern_confidence));
            
            // Filing risk: original is 0-100 (high risk = lower desirability). Let's invert risk to score for consistency (>70 is lime).
            const riskRaw = cached?.filings?.risk_score !== undefined ? parseValue(cached.filings.risk_score) : parseValue();
            const filingScore = 100 - riskRaw; 
            
            // OI and CA are mocked
            // Create a seed based on symbol length to make mock stable per stock
            const stableSeed = s.length * 10 + s.charCodeAt(0);
            const oiScore = (stableSeed * 7) % 100;
            const caScore = (stableSeed * 13) % 100;
            
            const scores = [
                { val: promoterScore, label: rawPromoter > 0 ? "BUYING" : "SELLING", desc: "Strong insider accumulation detected over consecutive quarters" },
                { val: expiryScore, label: cached?.expiry?.pattern || "PATTERN", desc: "Strong historical correlation with pre-expiry rallies" },
                { val: filingScore, label: riskRaw > 60 ? "HIGH RISK" : (riskRaw < 30 ? "CLEAN" : "NEUTRAL"), desc: riskRaw > 60 ? "Multiple high-risk corporate governance filings detected recently" : "Historical filings show clean corporate governance" },
                { val: oiScore, label: oiScore > 50 ? "BUILDUP" : "UNWIND", desc: "Abnormal open interest buildup suggests impending breakout" },
                { val: caScore, label: caScore > 70 ? "IMMINENT" : "QUIET", desc: "Approaching a significant ex-date for corporate action" }
            ];
            
            // Find highest opportunity
            scores.forEach((sc, idx) => {
                if (!bestSignal || sc.val > bestSignal.score) {
                    bestSignal = {
                        score: sc.val,
                        stock: s,
                        type: dimensions[idx],
                        desc: sc.desc
                    };
                }
            });
            
            // Label Row
            html += `<div style="font-weight: bold; color: #fff; display: flex; align-items: center;">${s}</div>`;
            
            // Cells
            scores.forEach(sc => {
                const color = getBgColor(sc.val);
                const textColor = sc.val > 70 ? '#c8ff00' : (sc.val < 30 ? '#ff4444' : '#fff');
                
                html += `
                    <div style="background: ${color}; padding: 15px; display: flex; flex-direction: column; justify-content: center; align-items: center; border-radius: 4px;">
                        <span style="font-size: 24px; font-weight: bold; color: ${textColor}; line-height: 1;">${sc.val}</span>
                        <span style="font-size: 10px; color: #666; margin-top: 8px; text-transform: uppercase;">${sc.label}</span>
                    </div>
                `;
            });
        });
        
        compositeGrid.innerHTML = html;
        
        if (bestSignal) {
            highestSignal.innerHTML = `${bestSignal.stock} &mdash; ${bestSignal.type}: ${bestSignal.desc}.`;
        }
    }

});