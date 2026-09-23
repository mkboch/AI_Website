"use strict";


function forcePageTop() {
    window.scrollTo({
        top: 0,
        left: 0,
        behavior: "auto"
    });
}

if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
}

window.addEventListener("load", function() {
    forcePageTop();

    window.setTimeout(
        forcePageTop,
        0
    );

    window.setTimeout(
        forcePageTop,
        50
    );
});

window.addEventListener("pageshow", function() {
    forcePageTop();
});

var state = {
    currentData: null,
    currentItems: [],
    items: [],
    filtered: [],
    page: 1,
    perPage: 18,
    search: "",
    category: "all",
    type: "all",
    source: "all",
    sort: "priority",
    mode: "current",
    archiveIndex: null
};

function el(id) { return document.getElementById(id); }
function normalize(value) { return String(value || "").toLowerCase().trim(); }
function escapeHTML(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
function safeURL(value) {
    try {
        var parsed = new URL(value);
        return (parsed.protocol === "https:" || parsed.protocol === "http:") ? escapeHTML(parsed.href) : "#";
    } catch (error) { return "#"; }
}
function parseDate(value) {
    if (!value) return null;
    var date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}
function formatDate(value) {
    var date = parseDate(value);
    if (!date) return "Date unavailable";
    return new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric"}).format(date);
}
function formatDateTime(value) {
    var date = parseDate(value);
    if (!date) return "Not yet refreshed";
    return new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit"}).format(date);
}
function truncateText(value, maxLength) {
    var text = String(value || "").trim();
    if (text.length <= maxLength) return text;
    return text.slice(0, maxLength - 1).trim() + "…";
}
function unique(values) { return Array.from(new Set(values.filter(Boolean))).sort(); }

function animateCount(id, target, duration) {
    var node = el(id);
    if (!node) return;

    target = Math.max(0, Number(target || 0));
    duration = Number(duration || 900);

    var reduceMotion = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion) {
        node.textContent = Math.round(target).toLocaleString();
        return;
    }

    node.textContent = "0";

    var startTime = null;

    function update(timestamp) {
        if (startTime === null) startTime = timestamp;

        var elapsed = timestamp - startTime;
        var progress = Math.min(elapsed / duration, 1);

        // Smooth ease-out animation.
        var eased = 1 - Math.pow(1 - progress, 3);

        var current = Math.round(
            target * eased
        );

        node.textContent =
            current.toLocaleString();

        if (progress < 1) {
            window.requestAnimationFrame(update);
        } else {
            node.textContent =
                Math.round(target).toLocaleString();
        }
    }

    window.requestAnimationFrame(update);
}

function fetchJSON(path) {
    return fetch(path + (path.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now(), {cache: "no-store"})
        .then(function(response) {
            if (!response.ok) throw new Error("HTTP " + response.status + " for " + path);
            return response.json();
        });
}

function getCategories() { return unique(state.items.map(function(item) { return item.category; })); }
function getTypes() { return unique(state.items.map(function(item) { return item.content_type; })); }
function getSources() { return unique(state.items.map(function(item) { return item.source; })); }

function populateSelect(select, values, allLabel, selected) {
    select.innerHTML = "";
    var first = document.createElement("option");
    first.value = "all";
    first.textContent = allLabel;
    select.appendChild(first);
    values.forEach(function(value) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    });
    select.value = values.indexOf(selected) >= 0 ? selected : "all";
}

function populateFilters() {
    populateSelect(el("category-filter"), getCategories(), "All topics", state.category);
    populateSelect(el("type-filter"), getTypes(), "All types", state.type);
    populateSelect(el("source-filter"), getSources(), "All sources", state.source);
    renderCategoryButtons(getCategories());
}

function renderCategoryButtons(categories) {
    var priority = [
        "Medical Imaging", "Medical AI", "Trustworthy AI", "Foundation Models", "AI Agents",
        "AI4Education", "AI for Science", "Computer Vision", "Robotics & Embodied AI",
        "AI Systems & Hardware", "AI Policy & Governance", "General AI"
    ];
    var available = priority.filter(function(value) { return categories.indexOf(value) >= 0; });
    var buttons = ["all"].concat(available);
    var holder = el("category-buttons");
    holder.innerHTML = "";
    buttons.forEach(function(category) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "category-button" + (state.category === category ? " active" : "");
        button.textContent = category === "all" ? "All" : category;
        button.addEventListener("click", function() {
            state.category = category;
            state.page = 1;
            el("category-filter").value = category;
            renderCategoryButtons(categories);
            applyFilters();
        });
        holder.appendChild(button);
    });
}

function badge(text, cls) {
    if (!text) return "";
    return '<span class="mini-badge ' + escapeHTML(cls || "") + '">' + escapeHTML(text) + "</span>";
}

function metadataLine(item) {
    var parts = [];
    if (item.venue) parts.push(escapeHTML(item.venue));
    if (item.publication_status && item.publication_status !== item.content_type) parts.push(escapeHTML(item.publication_status));
    if (item.related && item.related.length) parts.push(escapeHTML(String(item.related.length)) + " related source" + (item.related.length > 1 ? "s" : ""));
    return parts.length ? '<div class="card-extra">' + parts.join(" · ") + "</div>" : "";
}

function createCard(item) {
    var topClass = Number(item.rank || 999) <= 3 ? " top-ranked" : "";
    var images = itemImages(item);
    var visualClass = images.length ? " has-media" : " has-fallback";

    var html = '<article class="news-card'
        + topClass
        + visualClass
        + '">';

    html += cardMedia(item);

    html += '<div class="card-line"></div>';
    html += '<div class="card-body">';

    html += '<div class="card-badges">';
    html += badge(
        item.content_type || "Signal",
        "type-badge"
    );
    html += badge(
        item.category || "General AI",
        "category-badge"
    );

    if (
        item.priority_label === "Top signal"
        || item.priority_label === "High relevance"
    ) {
        html += badge(
            item.priority_label,
            "priority-badge"
        );
    }

    html += "</div>";

    html += '<div class="card-date">'
        + escapeHTML(formatDate(item.date))
        + "</div>";

    html += "<h3>"
        + escapeHTML(item.title || "")
        + "</h3>";

    html += "<p>"
        + escapeHTML(
            truncateText(
                item.excerpt
                    || "Open the original source for details.",
                300
            )
        )
        + "</p>";

    html += metadataLine(item);

    html += '<div class="card-footer">';

    html += '<span class="source-name">'
        + escapeHTML(item.source || "Source")
        + "</span>";

    html += '<a class="read-link" '
        + 'target="_blank" '
        + 'rel="noopener noreferrer" '
        + 'href="'
        + safeURL(item.url)
        + '">Original &rarr;</a>';

    html += "</div>";
    html += "</div>";
    html += "</article>";

    return html;
}

function selectFeatured(items, count) {
    var pool = items.slice().sort(function(a, b) {
        return Number(b.priority_score || 0) - Number(a.priority_score || 0);
    }).slice(0, 60);

    var selected = [];

    while (selected.length < count && pool.length) {
        var bestIndex = 0;
        var bestScore = -Infinity;

        pool.forEach(function(item, index) {
            var score = Number(item.priority_score || 0);

            selected.forEach(function(chosen) {
                if (item.source === chosen.source) score -= 24;
                if (item.content_type === chosen.content_type) score -= 7;
                if (item.category === chosen.category) score -= 6;
            });

            if (score > bestScore) {
                bestScore = score;
                bestIndex = index;
            }
        });

        selected.push(pool.splice(bestIndex, 1)[0]);
    }

    return selected;
}

function itemImages(item) {
    var values = Array.isArray(item.images) ? item.images : [];
    var seen = {};

    return values.filter(function(value) {
        try {
            var parsed = new URL(String(value || ""));
            if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return false;
            if (seen[parsed.href]) return false;
            seen[parsed.href] = true;
            return true;
        } catch (error) {
            return false;
        }
    }).slice(0, 4);
}

function featuredMedia(item) {
    var images = itemImages(item);

    if (!images.length) return "";

    var slides = images.map(function(url, index) {
        var loading = index === 0 ? "eager" : "lazy";

        return '<div class="featured-media-slide">'
            + '<img src="' + safeURL(url) + '" '
            + 'alt="' + escapeHTML((item.title || "Research signal") + " image " + (index + 1)) + '" '
            + 'loading="' + loading + '" '
            + 'decoding="async" '
            + 'draggable="false">'
            + '</div>';
    }).join("");

    var dots = "";

    if (images.length > 1) {
        dots = '<div class="featured-media-dots" aria-hidden="true">'
            + images.map(function(_, index) {
                return '<span class="featured-media-dot'
                    + (index === 0 ? " active" : "")
                    + '"></span>';
            }).join("")
            + '</div>';
    }

    return '<div class="featured-media" data-carousel-count="' + images.length + '">'
        + '<div class="featured-media-track">' + slides + '</div>'
        + dots
        + '</div>';
}


function categoryVisualClass(category) {
    var classes = {
        "Medical Imaging": "fallback-medical-imaging",
        "Medical AI": "fallback-medical-ai",
        "Trustworthy AI": "fallback-trustworthy",
        "Foundation Models": "fallback-foundation",
        "AI Agents": "fallback-agents",
        "AI4Education": "fallback-education",
        "AI for Science": "fallback-science",
        "Computer Vision": "fallback-vision",
        "Robotics & Embodied AI": "fallback-robotics",
        "AI Systems & Hardware": "fallback-systems",
        "AI Policy & Governance": "fallback-policy",
        "General AI": "fallback-general"
    };

    return classes[category] || "fallback-general";
}

function categoryFallback(item) {
    var category = item.category || "General AI";

    return '<div class="card-fallback '
        + categoryVisualClass(category)
        + '" aria-hidden="true">'
        + '<div class="card-fallback-mark">AI</div>'
        + '<div class="card-fallback-content">'
        + '<span>WANG-AXIS</span>'
        + '<strong>'
        + escapeHTML(category)
        + '</strong>'
        + '<small>Research Intelligence</small>'
        + '</div>'
        + '</div>';
}

function cardMedia(item) {
    var images = itemImages(item);

    if (!images.length) {
        return categoryFallback(item);
    }

    var media = featuredMedia(item);

    return media.replace(
        'class="featured-media"',
        'class="featured-media card-media"'
    );
}

function setFeaturedSlide(carousel, index) {
    var track = carousel.querySelector(".featured-media-track");
    var slides = carousel.querySelectorAll(".featured-media-slide");
    var dots = carousel.querySelectorAll(".featured-media-dot");

    if (!track || !slides.length) return;

    var count = slides.length;
    var normalized = ((index % count) + count) % count;

    carousel.dataset.carouselIndex = String(normalized);
    track.style.transform = "translateX(-" + (normalized * 100) + "%)";

    dots.forEach(function(dot, dotIndex) {
        dot.classList.toggle("active", dotIndex === normalized);
    });
}

function initFeaturedCarousels(holder) {
    var reduceMotion = window.matchMedia
        && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    holder.querySelectorAll(".featured-media").forEach(function(carousel) {
        var slides = carousel.querySelectorAll(".featured-media-slide");

        carousel.dataset.carouselIndex = "0";

        slides.forEach(function(slide) {
            var image = slide.querySelector("img");

            if (!image) return;

            image.addEventListener("error", function() {
                image.hidden = true;
                slide.classList.add("image-failed");
            });
        });

        if (slides.length <= 1 || reduceMotion) return;

        var delayTimer = null;
        var intervalTimer = null;
        var touchStartX = null;

        function currentIndex() {
            return Number(carousel.dataset.carouselIndex || 0);
        }

        function advance() {
            setFeaturedSlide(
                carousel,
                currentIndex() + 1
            );
        }

        function stop(reset) {
            if (delayTimer) {
                window.clearTimeout(delayTimer);
                delayTimer = null;
            }

            if (intervalTimer) {
                window.clearInterval(intervalTimer);
                intervalTimer = null;
            }

            if (reset) {
                setFeaturedSlide(
                    carousel,
                    0
                );
            }
        }

        function start() {
            stop(false);

            delayTimer = window.setTimeout(function() {
                advance();

                intervalTimer = window.setInterval(
                    advance,
                    1700
                );
            }, 650);
        }

        carousel.addEventListener(
            "mouseenter",
            start
        );

        carousel.addEventListener(
            "mouseleave",
            function() {
                stop(true);
            }
        );

        carousel.addEventListener(
            "touchstart",
            function(event) {
                if (!event.touches || !event.touches.length) return;
                touchStartX = event.touches[0].clientX;
            },
            {passive: true}
        );

        carousel.addEventListener(
            "touchend",
            function(event) {
                if (touchStartX === null) return;
                if (!event.changedTouches || !event.changedTouches.length) return;

                var delta = event.changedTouches[0].clientX - touchStartX;

                if (Math.abs(delta) >= 35) {
                    setFeaturedSlide(
                        carousel,
                        currentIndex() + (delta < 0 ? 1 : -1)
                    );
                }

                touchStartX = null;
            },
            {passive: true}
        );
    });
}

function renderFeatured(items) {
    var holder = el("featured");
    var featured = selectFeatured(items, 3);

    if (!featured.length) {
        holder.innerHTML = '<div class="loading-panel">No featured signals available.</div>';
        return;
    }

    holder.innerHTML = featured.map(function(item, index) {
        var images = itemImages(item);
        var media = featuredMedia(item);
        var html = '<article class="featured-card' + (images.length ? " has-media" : "") + '">';

        html += media;
        html += '<div class="featured-content">';
        html += '<div class="featured-number">0' + (index + 1) + "</div>";
        html += '<div class="featured-meta">' + badge(item.content_type, "type-badge") + badge(item.category, "category-badge") + "</div>";
        html += "<h3>" + escapeHTML(item.title) + "</h3>";
        html += "<p>" + escapeHTML(truncateText(item.excerpt || "", 360)) + "</p>";
        html += '<div class="featured-footer"><span>' + escapeHTML(item.source) + " &middot; " + escapeHTML(formatDate(item.date)) + "</span>";
        html += '<a target="_blank" rel="noopener noreferrer" href="' + safeURL(item.url) + '">Read source &rarr;</a></div>';
        html += "</div>";
        html += "</article>";

        return html;
    }).join("");

    initFeaturedCarousels(holder);
}

function applyFilters() {
    var query = normalize(state.search);
    var filtered = state.items.filter(function(item) {
        var categoryMatch = state.category === "all" || item.category === state.category || (item.categories || []).indexOf(state.category) >= 0;
        var typeMatch = state.type === "all" || item.content_type === state.type;
        var sourceMatch = state.source === "all" || item.source === state.source;
        var searchable = normalize([
            item.title, item.excerpt, item.source, item.source_class, item.category,
            (item.categories || []).join(" "), (item.tags || []).join(" "), item.venue,
            (item.authors || []).join(" "), item.publication_status
        ].join(" "));
        return categoryMatch && typeMatch && sourceMatch && (query === "" || searchable.indexOf(query) >= 0);
    });

    filtered.sort(function(a, b) {
        var aDate = parseDate(a.date), bDate = parseDate(b.date);
        var aTime = aDate ? aDate.getTime() : 0, bTime = bDate ? bDate.getTime() : 0;
        if (state.sort === "oldest") return aTime - bTime;
        if (state.sort === "newest") return bTime - aTime;
        var scoreDelta = Number(b.priority_score || 0) - Number(a.priority_score || 0);
        return scoreDelta !== 0 ? scoreDelta : bTime - aTime;
    });
    state.filtered = filtered;
    renderGrid();
}

function renderGrid() {
    var end = state.page * state.perPage;
    var visible = state.filtered.slice(0, end);
    var grid = el("news-grid");

    grid.innerHTML = visible.map(createCard).join("");

    initFeaturedCarousels(
        grid
    );

    var count = state.filtered.length;
    el("result-count").textContent = count.toLocaleString() + (count === 1 ? " signal" : " signals") + (state.mode === "archive" ? " in this archive view" : " in the current feed");
    el("empty-state").hidden = count !== 0;
    el("news-grid").hidden = count === 0;
    el("load-more").hidden = count === 0 || end >= count;
}

function resetFilters() {
    state.search = ""; state.category = "all"; state.type = "all"; state.source = "all"; state.sort = "priority"; state.page = 1;
    el("search-input").value = "";
    el("sort-filter").value = "priority";
}

function useItems(items, mode, label) {
    state.items = Array.isArray(items) ? items : [];
    state.mode = mode;
    resetFilters();
    populateFilters();
    el("feed-title").textContent = label;
    el("return-current").hidden = mode === "current";
    applyFilters();
}

function renderStats(data) {
    var summary = data.source_summary || {};
    animateCount(
        "story-count",
        Number(data.item_count || state.currentItems.length),
        950
    );

    animateCount(
        "source-count",
        Number(summary.total_sources || 0),
        750
    );

    animateCount(
        "healthy-count",
        Number(summary.healthy_sources || 0),
        850
    );

    animateCount(
        "archive-count",
        Number(data.archive_item_count || 0),
        1100
    );
    el("last-updated").textContent = formatDateTime(data.updated_at);

    var failed = Number(summary.failed_sources || 0);
    var withItems = Number(summary.sources_with_items || 0);
    var healthy = Number(summary.healthy_sources || 0);
    var text = healthy + " sources reachable" + (withItems ? ", " + withItems + " contributed items" : "");
    if (failed) text += ", " + failed + " currently unavailable";
    el("health-banner").textContent = text;
    el("health-banner").className = "health-banner " + (failed ? "health-warn" : "health-ok");
}

function renderSourceHealth(data) {
    var summary = data.source_summary || {};
    var classCounts = summary.source_classes || {};
    var cards = Object.keys(classCounts).sort().map(function(name) {
        return '<div class="coverage-card"><strong>' + escapeHTML(String(classCounts[name])) + '</strong><span>' + escapeHTML(name) + "</span></div>";
    });
    el("source-summary").innerHTML = cards.join("");

    var health = data.source_health || [];
    el("source-health-list").innerHTML = health.map(function(item) {
        var status = item.status || "unknown";
        var cls = status === "error" ? "source-error" : (status === "empty" ? "source-empty" : "source-ok");
        var detail = item.accepted + " accepted / " + item.fetched + " fetched";
        if (item.error) detail += " · " + item.error;
        return '<div class="source-row"><span class="source-dot ' + cls + '"></span><div><strong>' + escapeHTML(item.name) + '</strong><span>' + escapeHTML(item.source_class || "") + " · " + escapeHTML(detail) + "</span></div></div>";
    }).join("");
}

function renderArchiveIndex(index) {
    state.archiveIndex = index;
    var select = el("archive-select");
    select.innerHTML = "";
    var months = index && Array.isArray(index.months) ? index.months : [];
    if (!months.length) {
        var empty = document.createElement("option"); empty.value = ""; empty.textContent = "No archive months yet"; select.appendChild(empty);
        el("archive-load").disabled = true; return;
    }
    months.forEach(function(entry) {
        var option = document.createElement("option");
        option.value = entry.file;
        option.textContent = entry.month + " · " + Number(entry.item_count || 0).toLocaleString() + " signals";
        select.appendChild(option);
    });
    el("archive-load").disabled = false;
    el("archive-status").textContent = Number(index.total_items || 0).toLocaleString() + " archived signals across " + months.length + " month" + (months.length === 1 ? "" : "s") + ".";
}

function loadCurrent() {
    return fetchJSON("data/news.json").then(function(data) {
        state.currentData = data;
        state.currentItems = Array.isArray(data.items) ? data.items : [];
        renderStats(data);
        renderFeatured(state.currentItems);
        renderSourceHealth(data);
        useItems(state.currentItems, "current", "Current intelligence");
    });
}

function loadArchive() {
    var path = el("archive-select").value;
    if (!path) return;
    el("archive-status").textContent = "Loading archive…";
    fetchJSON(path).then(function(data) {
        var items = Array.isArray(data.items) ? data.items : [];
        useItems(items, "archive", "Archive · " + (data.month || "selected month"));
        el("archive-status").textContent = items.length.toLocaleString() + " signals loaded from " + (data.month || "archive") + ".";
        document.getElementById("news").scrollIntoView({behavior: "smooth"});
    }).catch(function(error) {
        console.error(error);
        el("archive-status").textContent = "Archive could not be loaded.";
    });
}

var searchTimer = null;
el("search-input").addEventListener("input", function(event) {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function() { state.search = event.target.value; state.page = 1; applyFilters(); }, 120);
});
el("category-filter").addEventListener("change", function(event) { state.category = event.target.value; state.page = 1; renderCategoryButtons(getCategories()); applyFilters(); });
el("type-filter").addEventListener("change", function(event) { state.type = event.target.value; state.page = 1; applyFilters(); });
el("source-filter").addEventListener("change", function(event) { state.source = event.target.value; state.page = 1; applyFilters(); });
el("sort-filter").addEventListener("change", function(event) { state.sort = event.target.value; state.page = 1; applyFilters(); });
el("load-more").addEventListener("click", function() { state.page += 1; renderGrid(); });
el("archive-load").addEventListener("click", loadArchive);
el("return-current").addEventListener("click", function() { useItems(state.currentItems, "current", "Current intelligence"); renderFeatured(state.currentItems); });
el("year").textContent = new Date().getFullYear();

Promise.all([
    loadCurrent(),
    fetchJSON("data/archive/index.json").then(renderArchiveIndex).catch(function() { renderArchiveIndex({months: [], total_items: 0}); })
]).catch(function(error) {
    console.error(error);
    el("health-banner").textContent = "Feed unavailable";
    el("featured").innerHTML = '<div class="loading-panel">The current feed could not be loaded.</div>';
    el("news-grid").innerHTML = "";
    el("result-count").textContent = "Feed unavailable";
});
