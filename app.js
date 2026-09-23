"use strict";

var state = {
    items: [],
    filtered: [],
    page: 1,
    perPage: 18,
    search: "",
    category: "all",
    source: "all",
    sort: "newest"
};

var storyCount = document.getElementById("story-count");
var sourceCount = document.getElementById("source-count");
var lastUpdated = document.getElementById("last-updated");

var featured = document.getElementById("featured");

var searchInput = document.getElementById("search-input");
var categoryFilter = document.getElementById("category-filter");
var sourceFilter = document.getElementById("source-filter");
var sortFilter = document.getElementById("sort-filter");

var categoryButtons = document.getElementById("category-buttons");

var newsGrid = document.getElementById("news-grid");
var loadMore = document.getElementById("load-more");
var emptyState = document.getElementById("empty-state");
var resultCount = document.getElementById("result-count");

var yearElement = document.getElementById("year");


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

        if (
            parsed.protocol === "https:" ||
            parsed.protocol === "http:"
        ) {
            return escapeHTML(parsed.href);
        }
    } catch (error) {
        return "#";
    }

    return "#";
}


function normalize(value) {
    return String(value || "").toLowerCase().trim();
}


function parseDate(value) {
    if (!value) {
        return null;
    }

    var date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return null;
    }

    return date;
}


function formatDate(value) {
    var date = parseDate(value);

    if (!date) {
        return "Date unavailable";
    }

    return new Intl.DateTimeFormat(
        "en-US",
        {
            month: "short",
            day: "numeric",
            year: "numeric"
        }
    ).format(date);
}


function formatDateTime(value) {
    var date = parseDate(value);

    if (!date) {
        return "Not yet refreshed";
    }

    return new Intl.DateTimeFormat(
        "en-US",
        {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit"
        }
    ).format(date);
}


function truncateText(value, maxLength) {
    var text = String(value || "").trim();

    if (text.length <= maxLength) {
        return text;
    }

    return text.slice(0, maxLength - 1).trim() + "…";
}


function getCategories() {
    var values = state.items
        .map(function(item) {
            return item.category;
        })
        .filter(Boolean);

    return Array.from(new Set(values)).sort();
}


function getSources() {
    var values = state.items
        .map(function(item) {
            return item.source;
        })
        .filter(Boolean);

    return Array.from(new Set(values)).sort();
}


function populateFilters() {
    var categories = getCategories();
    var sources = getSources();

    categoryFilter.innerHTML =
        '<option value="all">All categories</option>';

    categories.forEach(function(category) {
        var option = document.createElement("option");

        option.value = category;
        option.textContent = category;

        categoryFilter.appendChild(option);
    });

    sourceFilter.innerHTML =
        '<option value="all">All sources</option>';

    sources.forEach(function(source) {
        var option = document.createElement("option");

        option.value = source;
        option.textContent = source;

        sourceFilter.appendChild(option);
    });

    renderCategoryButtons(categories);
}


function renderCategoryButtons(categories) {
    var priority = [
        "Medical Imaging",
        "Medical AI",
        "Foundation Models",
        "AI Agents",
        "Trustworthy AI",
        "AI for Science",
        "Computer Vision",
        "AI4Education",
        "General AI"
    ];

    var available = priority.filter(function(value) {
        return categories.indexOf(value) >= 0;
    });

    var buttons = ["all"].concat(available);

    categoryButtons.innerHTML = "";

    buttons.forEach(function(category) {
        var button = document.createElement("button");

        button.type = "button";
        button.className = "category-button";

        if (state.category === category) {
            button.className += " active";
        }

        button.dataset.category = category;
        button.textContent = category === "all" ? "All" : category;

        button.addEventListener("click", function() {
            state.category = category;
            state.page = 1;

            categoryFilter.value = category;

            renderCategoryButtons(categories);
            applyFilters();
        });

        categoryButtons.appendChild(button);
    });
}


function renderFeatured(item) {
    if (!item) {
        featured.innerHTML =
            '<div class="loading-panel">No stories are available yet.</div>';

        return;
    }

    var html = "";

    html += '<article class="featured-card">';

    html += '<div class="featured-visual">';

    html += '<div class="featured-badge">';
    html += escapeHTML(item.category || "Artificial Intelligence");
    html += '</div>';

    html += '<div class="featured-source-large">';
    html += escapeHTML(item.source || "Research source");
    html += '</div>';

    html += '</div>';

    html += '<div class="featured-content">';

    html += '<div class="featured-meta">';

    html += '<span class="category">';
    html += escapeHTML(item.category || "AI");
    html += '</span>';

    html += '<span>•</span>';

    html += '<span>';
    html += escapeHTML(formatDate(item.date));
    html += '</span>';

    html += '</div>';

    html += '<h3>';
    html += escapeHTML(item.title || "");
    html += '</h3>';

    html += '<p>';
    html += escapeHTML(
        truncateText(
            item.excerpt ||
            "Open the original source for the full article.",
            370
        )
    );
    html += '</p>';

    html += '<a class="featured-link" target="_blank" rel="noopener noreferrer" href="';
    html += safeURL(item.url);
    html += '">';
    html += 'Read original source →';
    html += '</a>';

    html += '</div>';

    html += '</article>';

    featured.innerHTML = html;
}


function createCard(item) {
    var html = "";

    html += '<article class="news-card">';

    html += '<div class="card-line"></div>';

    html += '<div class="card-body">';

    html += '<div class="card-top">';

    html += '<span class="card-category">';
    html += escapeHTML(item.category || "General AI");
    html += '</span>';

    html += '<span class="card-date">';
    html += escapeHTML(formatDate(item.date));
    html += '</span>';

    html += '</div>';

    html += '<h3>';
    html += escapeHTML(item.title || "");
    html += '</h3>';

    html += '<p>';
    html += escapeHTML(
        truncateText(
            item.excerpt ||
            "Open the original source for additional information.",
            245
        )
    );
    html += '</p>';

    html += '<div class="card-footer">';

    html += '<span class="source-name">';
    html += escapeHTML(item.source || "Source");
    html += '</span>';

    html += '<a class="read-link" target="_blank" rel="noopener noreferrer" href="';
    html += safeURL(item.url);
    html += '">';
    html += 'Read →';
    html += '</a>';

    html += '</div>';

    html += '</div>';

    html += '</article>';

    return html;
}


function renderGrid() {
    var end = state.page * state.perPage;

    var visible = state.filtered.slice(0, end);

    newsGrid.innerHTML = visible
        .map(createCard)
        .join("");

    var count = state.filtered.length;

    resultCount.textContent =
        count === 1
        ? "1 story"
        : count.toLocaleString() + " stories";

    if (count === 0) {
        emptyState.hidden = false;
        newsGrid.hidden = true;
    } else {
        emptyState.hidden = true;
        newsGrid.hidden = false;
    }

    loadMore.hidden =
        count === 0 ||
        end >= count;
}


function applyFilters() {
    var query = normalize(state.search);

    var filtered = state.items.filter(function(item) {
        var categoryMatch =
            state.category === "all" ||
            item.category === state.category;

        var sourceMatch =
            state.source === "all" ||
            item.source === state.source;

        var searchable = normalize(
            [
                item.title,
                item.excerpt,
                item.source,
                item.category,
                (item.tags || []).join(" ")
            ].join(" ")
        );

        var searchMatch =
            query === "" ||
            searchable.indexOf(query) >= 0;

        return categoryMatch && sourceMatch && searchMatch;
    });

    filtered.sort(function(a, b) {
        var aDate = parseDate(a.date);
        var bDate = parseDate(b.date);

        var aTime = aDate ? aDate.getTime() : 0;
        var bTime = bDate ? bDate.getTime() : 0;

        if (state.sort === "oldest") {
            return aTime - bTime;
        }

        return bTime - aTime;
    });

    state.filtered = filtered;

    renderGrid();
}


function updateStats(data) {
    storyCount.textContent =
        state.items.length.toLocaleString();

    sourceCount.textContent =
        getSources().length.toLocaleString();

    lastUpdated.textContent =
        formatDateTime(data.updated_at);
}


var searchTimer = null;

searchInput.addEventListener("input", function(event) {
    clearTimeout(searchTimer);

    searchTimer = setTimeout(function() {
        state.search = event.target.value;
        state.page = 1;

        applyFilters();
    }, 150);
});


categoryFilter.addEventListener("change", function(event) {
    state.category = event.target.value;
    state.page = 1;

    renderCategoryButtons(getCategories());

    applyFilters();
});


sourceFilter.addEventListener("change", function(event) {
    state.source = event.target.value;
    state.page = 1;

    applyFilters();
});


sortFilter.addEventListener("change", function(event) {
    state.sort = event.target.value;
    state.page = 1;

    applyFilters();
});


loadMore.addEventListener("click", function() {
    state.page += 1;

    renderGrid();
});


async function loadNews() {
    try {
        var response = await fetch(
            "data/news.json?version=" + Date.now(),
            {
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error(
                "HTTP " + response.status
            );
        }

        var data = await response.json();

        if (Array.isArray(data.items)) {
            state.items = data.items;
        } else {
            state.items = [];
        }

        state.items.sort(function(a, b) {
            var aDate = parseDate(a.date);
            var bDate = parseDate(b.date);

            var aTime = aDate ? aDate.getTime() : 0;
            var bTime = bDate ? bDate.getTime() : 0;

            return bTime - aTime;
        });

        updateStats(data);
        populateFilters();

        renderFeatured(
            state.items.length > 0
            ? state.items[0]
            : null
        );

        applyFilters();

    } catch (error) {
        console.error(error);

        storyCount.textContent = "0";
        sourceCount.textContent = "0";
        lastUpdated.textContent = "Feed unavailable";

        featured.innerHTML =
            '<div class="loading-panel">The news feed could not be loaded.</div>';

        newsGrid.innerHTML = "";

        resultCount.textContent =
            "News feed unavailable";
    }
}


yearElement.textContent =
    new Date().getFullYear();

loadNews();