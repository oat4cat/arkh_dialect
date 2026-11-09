/* CSRF-защита для Django*/
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrftoken = getCookie('csrftoken');
$.ajaxSetup({
    beforeSend: function (xhr, settings) {
        if (!/^http:.*/.test(settings.url) && !/^https:.*/.test(settings.url)) {
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    }
});


/**
 * Загрузка фильтров частей речи, районов 
 */
function loadSimpleFilter(apiUrl, containerId, selectedContainerId) {
    $.ajax({
        url: apiUrl,
        type: 'GET',
        success: function (data) {
            const container = $(`#${containerId}`);
            container.empty();

            data.forEach(item => {
                const value = item.name || item; // name для регионов, строка для pos
                const label = item.name || item; // ??? тут надо нормально сделать

                const btn = $(`<button class="filter" data="${value}">${label}</button>`);

                // Обработчик клика
                btn.click(function () {
                    $(this).toggleClass('active');
                    const selectedContainer = $(`#${selectedContainerId}`);

                    if ($(this).hasClass('active')) {
                        // Добавляем тег, если его ещё нет
                        if (!selectedContainer.find(`.selected-item[data="${value}"]`).length) {
                            selectedContainer.append(createSelectedTag(label, value));
                        }
                    } else {
                        // Удаляем тег
                        selectedContainer.find(`.selected-item[data="${value}"]`).remove();
                    }

                    // Перезапускаем поиск
                    filterWords(getFilters(false));
                });

                container.append(btn);
            });
        },
        error: function (err) {
            console.error(`Ошибка загрузки ${apiUrl}:`, err);
        }
    });
}

/**
 * Загрузка фильтров категорий и подкатегорий
 */
function loadCategories() {
    $.ajax({
        url: '/api/categories/',
        type: 'GET',
        success: function (data) {
            const container = $('#dropdown-content-subcategory');
            container.empty();

            data.forEach(cat => {
                const catId = cat.category.replace(/\s+/g, '-');

                // Кнопка категории (только для раскрытия, не для выбора)
                const catBtn = $(`
                    <button class="optgroup-button" id="optgroup-button-${catId}" 
                            onclick="toggleSubcategory('${catId}'); event.stopPropagation();">
                        ${cat.category}
                    </button>
                `);
                container.append(catBtn);

                // Контейнер с подкатегориями
                const subcatContainer = $(`
                    <div class="subcategory-filters" id="subcategory-filters-${catId}" style="display: none;"></div>
                `);

                cat.subcategories.forEach(subcat => {
                    const value = subcat.name;
                    const subBtn = $(`<button class="filter" data="${value}">${value}</button>`);

                    // Обработчик клика по подкатегории
                    subBtn.click(function () {
                        $(this).toggleClass('active');
                        const selectedContainer = $('#selected-items-subcategory');

                        if ($(this).hasClass('active')) {
                            if (!selectedContainer.find(`.selected-item[data="${value}"]`).length) {
                                selectedContainer.append(createSelectedTag(value, value));
                            }
                        } else {
                            selectedContainer.find(`.selected-item[data="${value}"]`).remove();
                        }

                        filterWords(getFilters(false));
                    });

                    subcatContainer.append(subBtn);
                });

                container.append(subcatContainer);
            });
        },
        error: function (err) {
            console.error('Ошибка загрузки категорий:', err);
        }
    });
}

/**
 * Добавление фильтра в список выбранных
 *
 * @param {string} label - название тега для пользователя
 * @param {string} value - значение тега для поиска по базе 
 */
function createSelectedTag(label, value) {
    const tag = document.createElement('div');
    tag.className = 'selected-item';
    tag.setAttribute('data', value);
    tag.innerHTML = `
        ${label}
        <span class="remove" onclick="removeFilter(this)">×</span>
    `;
    return tag;
}


/**
 * Удаление фильтр из списка выбранных
 *
 * @param {Object} element - объект span - крестик, потомок выбранного тега. 
 */
function removeFilter(element) {
    // Находим и чистим стили кнопки фильтра в дропдауне
    filter_div = $(element).parent()
    value = filter_div.attr('data');
    $(`.filter[data="${value}"]`).removeClass('active');

    // Удаляем тег
    filter_div.remove();
    filterWords(getFilters(false));
}

/* 3. Сбор текущих параметров фильтрации */
/**
 * Получает список выбранных фильтров и передаёт их в функцию фильтрации.
 * По умолчанию фильтрует с первой страницы
 *
 * @param {int} page_chosen - Ушёл ли пользователь с первой страницы, для пагинации.
 * @param {int} page_num - На какой странице находится пользователь, для пагинации.
 * 
 * @returns {dict} выбранные фильтры - слово, категория, район, часть речи,
 * текущая страница, сортировка
 */
function getFilters(page_chosen, page_num = 1) {
    $('.prolog, .prolog_list').hide();

    let order = 0;
    const activeOrder = $('.order-button.active');
    if (activeOrder.length) {
        order = parseInt(activeOrder.data('order')) || 0;
    }

    return {
        word: $('#word').val().toLowerCase(),
        subcategories: $('#selected-items-subcategory .selected-item').map(function () { return $(this).attr('data'); }).get(),
        regions: $('#selected-items-region .selected-item').map(function () { return $(this).attr('data'); }).get(),
        pos: $('#selected-items-pos .selected-item').map(function () { return $(this).attr('data'); }).get(),
        page: page_chosen ? parseInt($('.page-item.active').data('page')) || 1 : page_num,
        order: order
    };
}

/* 4. Запрос к Django API */
/**
 * Выполняет AJAX-запрос к серверу для поиска слов и обновления списка результатов.
 *
 * @param {Object} filters - Объект с параметрами фильтрации.
 * 
 * @returns {void}
 */
function filterWords(filters) {
    $.ajax({
        url: '/api/search/',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(filters),
        success: function (response) {
            renderResults(response.results);
            renderPagination(response);
        },
        error: function (err) {
            console.error('Ошибка запроса:', err);
            $('#words').html('<p style="color:red; padding: 20px;">Ошибка загрузки данных. Проверьте консоль разработчика.</p>');
        }
    });
}

/* 5. Отрисовка результатов */
/**
 * Формирует словарную статью
 *
 * @param {Object} word - Структура слова
 * @param {string} word.meaning - Значение слова
 * @param {string[]} word.examples - Примеры употребления с районами
 * 
 * @returns {Object} DOM-структура - словарная статья
 */
function createWordArticle(word) {
    const article = document.createElement('div');
    article.className = 'word';

    const header = createWordHeader(word);
    article.appendChild(header);

    if (word.meaning) {
        const meaning = document.createElement('div');
        meaning.className = 'word-meaning';
        meaning.innerHTML = escapeHtml(word.meaning);
        article.appendChild(meaning);
    }

    if (word.forms?.length) {
        const forms = document.createElement('div');
        forms.className = 'word-meaning';
        forms.textContent = `Формы: ${word.forms.map(form => {
            const grammar = form.grammatical_features
                ? ` (${form.grammatical_features})`
                : '';
            return `${form.accent || form.form}${grammar}`;
        }).join('; ')}`;
        article.appendChild(forms);
    }

    word.examples.forEach(ex => {
        const example = document.createElement('div');
        example.className = 'word-example';
        example.innerHTML = escapeHtml(ex.text);
        article.appendChild(example);

        if (ex.region) {
            const region = document.createElement('div');
            region.className = 'word-region';
            region.textContent = escapeHtml(ex.region);
            article.appendChild(region);
        }
    });

    article.appendChild(createGraphSection(word.word));

    return article;
}

/* 5.1 Граф понятий в карточке */
/**
 * Разворачиваемый раздел графа понятий. Ленивая загрузка: граф запрашивается
 * только при первом раскрытии раздела.
 *
 * @param {string} word - лексема карточки
 * @returns {Object} DOM-структура - раздел с кнопкой и контейнером графа
 */
function createGraphSection(word) {
    const section = document.createElement('div');
    section.className = 'word-graph';

    const toggle = document.createElement('button');
    toggle.className = 'word-graph-toggle';
    toggle.type = 'button';
    toggle.textContent = 'Связи через понятия';

    const body = document.createElement('div');
    body.className = 'word-graph-body';
    body.style.display = 'none';

    let loaded = false;
    toggle.addEventListener('click', function () {
        const opening = body.style.display === 'none';
        body.style.display = opening ? 'block' : 'none';
        toggle.classList.toggle('active', opening);
        if (opening && !loaded) {
            loaded = true;
            loadGraph(word, body);
        }
    });

    section.appendChild(toggle);
    section.appendChild(body);
    return section;
}

/**
 * Запрашивает граф понятий слова и передаёт контейнер в отрисовку
 *
 * @param {string} word - лексема карточки
 * @param {Object} container - DOM-контейнер под граф
 */
function loadGraph(word, container) {
    container.textContent = 'Загрузка связей…';
    $.ajax({
        url: '/api/graph/',
        type: 'GET',
        data: { word: word },
        success: function (data) {
            try {
                renderGraph(data, container);
            } catch (e) {
                container.textContent = 'Ошибка отрисовки графа: ' + e.message;
            }
        },
        error: function () {
            container.textContent = 'Не удалось загрузить связи.';
        }
    });
}

/**
 * Отрисовывает граф понятий через Cytoscape.js: слово → концепты → соседние
 * лексемы. Клик по лексеме — поиск слова; чипы подкатегорий под графом —
 * поиск по подкатегории; наведение на узел — подсказка со значением.
 * Непроверенные узлы помечаются пунктирной рамкой.
 *
 * @param {Object} data - ответ /api/graph/
 * @param {Object} container - DOM-контейнер под граф
 */
function renderGraph(data, container) {
    const senses = data.senses || [];
    if (!senses.length) {
        container.textContent = 'Связи через понятия не найдены.';
        return;
    }

    container.innerHTML = `
        <div class="word-graph-canvas"></div>
        <div class="word-graph-subcats"></div>
        <div class="word-graph-tooltip" style="display: none;"></div>
    `;
    const canvas = container.querySelector('.word-graph-canvas');
    const tooltip = container.querySelector('.word-graph-tooltip');
    const subcatsBox = container.querySelector('.word-graph-subcats');

    const elements = [];
    const nodeIds = new Set();
    const edgeIds = new Set();
    const subcats = new Set();
    const rootId = `w:${data.word}`;

    const addNode = (id, nodeData) => {
        if (nodeIds.has(id)) return;
        nodeIds.add(id);
        elements.push({ data: Object.assign({ id: id }, nodeData) });
    };
    const addEdge = (source, target) => {
        const key = `${source}->${target}`;
        if (edgeIds.has(key)) return;
        edgeIds.add(key);
        elements.push({ data: { id: `e:${key}`, source: source, target: target } });
    };

    addNode(rootId, { label: data.word, kind: 'root' });

    senses.forEach(sense => {
        sense.subcategories.forEach(name => subcats.add(name));
        sense.concepts.forEach(concept => {
            const conceptId = `c:${concept.concept_id}`;
            addNode(conceptId, {
                label: concept.name,
                kind: 'concept',
                unchecked: concept.status === 'unchecked'
            });
            addEdge(rootId, conceptId);
            concept.neighbors.forEach(n => {
                const neighborId = `w:${n.word}`;
                addNode(neighborId, {
                    label: n.accent || n.word,
                    kind: 'neighbor',
                    word: n.word,
                    unchecked: n.status === 'unchecked',
                    tooltip: n.meaning + (n.subcategories.length ? `\n${n.subcategories.join(', ')}` : '')
                });
                n.subcategories.forEach(name => subcats.add(name));
                addEdge(conceptId, neighborId);
            });
        });
    });

    if (subcats.size) {
        subcatsBox.textContent = 'Подкатегории: ';
        Array.from(subcats).slice(0, 8).forEach(name => {
            const chip = document.createElement('span');
            chip.className = 'graph-chip';
            chip.dataset.subcategory = name;
            chip.textContent = name;
            subcatsBox.appendChild(chip);
        });
    }

    const cy = cytoscape({
        container: canvas,
        elements: elements,
        minZoom: 0.4,
        maxZoom: 2.5,
        wheelSensitivity: 0.3,
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'width': 'label',
                    'height': 'label',
                    'padding': '6px',
                    'font-size': 13,
                    'font-family': 'Inter, sans-serif',
                    'color': '#002C5B',
                    'border-width': 1.5,
                    'border-color': '#002C5B'
                }
            },
            {
                selector: 'node[kind = "root"]',
                style: {
                    'background-color': '#ffffff',
                    'border-width': 2.5,
                    'font-weight': 'bold'
                }
            },
            {
                selector: 'node[kind = "concept"]',
                style: {
                    'background-color': '#ECEFF6',
                    'shape': 'round-rectangle'
                }
            },
            {
                selector: 'node[kind = "neighbor"]',
                style: {
                    'background-color': '#ffffff'
                }
            },
            {
                selector: 'node[?unchecked]',
                style: {
                    'border-style': 'dashed',
                    'opacity': 0.75
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 1.5,
                    'line-color': 'rgba(0, 44, 91, 0.35)',
                    'curve-style': 'bezier'
                }
            }
        ],
        layout: {
            name: 'cose',
            animate: false,
            idealEdgeLength: 90,
            nodeRepulsion: 6000,
            randomize: true
        }
    });

    // Клик по лексеме-соседу — поиск этого слова
    cy.on('tap', 'node[kind = "neighbor"]', function (event) {
        $('#word').val(event.target.data('word'));
        filterWords(getFilters(false));
    });

    // Наведение: курсор и подсказка со значением
    cy.on('mouseover', 'node', function (event) {
        const node = event.target;
        canvas.style.cursor = node.data('kind') === 'neighbor' ? 'pointer' : 'default';
        const text = node.data('tooltip');
        if (!text) return;
        tooltip.textContent = text;
        tooltip.style.display = 'block';
        const position = event.renderedPosition;
        tooltip.style.left = `${position.x + 14}px`;
        tooltip.style.top = `${position.y + 14}px`;
    });
    cy.on('mouseout', 'node', function () {
        tooltip.style.display = 'none';
    });

    $(container).on('click', '.graph-chip', function () {
        searchBySubcategory($(this).data('subcategory'));
    });
}

/**
 * Поиск по подкатегории: добавляет тег фильтра (как при выборе в дропдауне)
 * и запускает поиск существующим механизмом
 *
 * @param {string} name - название подкатегории
 */
function searchBySubcategory(name) {
    const selected = $('#selected-items-subcategory');
    if (!selected.find(`.selected-item[data="${name}"]`).length) {
        selected.append(createSelectedTag(name, name));
        $(`#dropdown-content-subcategory .filter[data="${name}"]`).addClass('active');
    }
    filterWords(getFilters(false));
}

/**
 * Формирует заголовок словарной статьи
 *
 * @param {Object} word - Структура слова
 * @param {string} word.word - Слово (без ударения).
 * @param {string} word.accent - Слово с ударением.
 * @param {string} word.grammatical_features - часть речи слова
 * @param {string[]} word.subcategories[] - подкатегории слова
 */
function createWordHeader(word) {
    const header = document.createElement('div');
    header.className = 'word-header';

    const wordDiv = document.createElement('div');
    wordDiv.className = 'word-word';

    const parts = (word.accent || '').trim().split(/\s+/);
    const mainWord = parts[0] || word.word;
    const subWord = parts.slice(1).join(' ');

    const mainSpan = document.createElement('span');
    mainSpan.textContent = mainWord;

    const subSpan = document.createElement('span');
    subSpan.className = 'word-subword';
    subSpan.textContent = `${subWord} ${escapeHtml(word.grammatical_features) || ''}`;

    wordDiv.appendChild(mainSpan);
    wordDiv.appendChild(subSpan);

    const categoryDiv = document.createElement('div');
    categoryDiv.className = 'word-category';
    categoryDiv.textContent = escapeHtml(word.subcategories.join(', ') || '');

    header.appendChild(wordDiv);
    header.appendChild(categoryDiv);

    return header;
}

/**
 * Формирует DOM-элементы словарных статей на основе полученных данных.
 *
 * @param {Object[]} words - Массив объектов слов от сервера.
 * @param {string} words[].word - Слово (без ударения).
 * @param {string} words[].accent - Слово с ударением.
 * @param {string} words[].meaning - Значение слова.
 * @param {Object[]} words[].examples - Массив примеров употребления.
 */
function renderResults(words) {
    const container = document.getElementById('words');
    container.innerHTML = '';

    if (!words || words.length === 0) {
        container.innerHTML = '<p style="padding: 20px;">Ничего не найдено. Попробуйте другой запрос.</p>';
        return;
    }

    let lastWord = '';
    let lastMeaning = '';
    let currentArticle = null;

    words.forEach(w => {
        const parts = (w.accent || '').trim().split(/\s+/);
        const mainWord = parts[0] || w.word;
        const subWord = parts.slice(1).join(' ');

        // Новая словарная статья
        if (w.word !== lastWord) {

            if (currentArticle) {
                container.appendChild(currentArticle);
            }

            currentArticle = createWordArticle(w);
            lastWord = w.word;
            lastMeaning = ''; // Сбрасываем для нового слова

        }
        else if (w.meaning && w.meaning !== lastMeaning) {
            const meaning = document.createElement('div');
            meaning.className = 'word-meaning';
            meaning.textContent = w.meaning;
            currentArticle.appendChild(meaning);
            lastMeaning = w.meaning;
        }

        else {
            w.examples?.forEach(ex => {
                if (ex.text?.trim()) {
                    const example = document.createElement('div');
                    example.className = 'word-example';
                    example.textContent = ex.text;
                    currentArticle.appendChild(example);
                }
                if (ex.region?.trim()) {
                    const region = document.createElement('div');
                    region.className = 'word-region';
                    region.textContent = ex.region;
                    currentArticle.appendChild(region);
                }
            });
        }
    });

    if (currentArticle) {
        container.appendChild(currentArticle);
    }
}

/* 6. Пагинация */
function generatePaginationHTML(total, current) {
    if (total <= 1) return '';
    const range = 2;
    let html = '';

    const addPage = (pageNum, isActive) => {
        const cls = isActive ? 'active' : '';
        const onclick = isActive ? '' : `onclick="pagination(this)"`;
        const ariaCurrent = isActive ? 'aria-current="page"' : '';
        html += `<li class="page-item ${cls}" data-page="${pageNum}" ${ariaCurrent} ${onclick}><span class="page-link">${pageNum}</span></li>`;
    };

    addPage(1, current === 1);

    let start = Math.max(current - range, range + 1);
    let end = Math.min(current + range, total - 1);

    if (start > 3) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
    if (start === 3) start = 2;
    if (total - end === 2) end += 1;

    for (let i = start; i <= end; i++) {
        addPage(i, current === i);
    }

    if (total - end > 2) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
    addPage(total, current === total);

    return html;
}

function renderPagination(data) {
    // Удаляем старую пагинацию
    const container = $('#pagination');
    container.empty();
    if (data.total_pages <= 1) return;

    const html = `
        <nav class="pagination-row">
            <ul class="pagination justify-content-center">
                <li class="page-item" onclick="to_page()"><span class="page-link">&nbsp;⮩&nbsp;</span></li>
                ${generatePaginationHTML(data.total_pages, data.current_page)}
            </ul>
        </nav>
        <div class="to_page page-item" style="display: none;">
            <span class="page-link">Перейти на страницу&nbsp;</span>
            <input type="text" class="input_field"/>
            <button class="submit_page" onclick="move_to_page()">→</button>
        </div>`;

    container.html(html);
}

function pagination(clickedElement) {
    $(clickedElement).addClass('active').siblings('.page-item').removeClass('active');
    filterWords(getFilters(true));
}

function to_page() {
    $('.to_page').toggle();
}

function move_to_page() {
    const pageNum = parseInt($('.to_page .input_field').val());
    if (pageNum && pageNum > 0) {
        filterWords(getFilters(false, pageNum));
    }
}

/* 7. Вспомогательные функции */
function toggleSubcategory(label) {
    const subcatFilters = document.getElementById('subcategory-filters-' + label);
    const btn = document.getElementById('optgroup-button-' + label);
    if (!subcatFilters || !btn) return;

    if (subcatFilters.style.display === 'none' || subcatFilters.style.display === '') {
        subcatFilters.style.display = 'block';
        subcatFilters.classList.add('open');
        btn.classList.add('active');
    } else {
        subcatFilters.style.display = 'none';
        subcatFilters.classList.remove('open');
        btn.classList.remove('active');
    }
}

function removeParams() {
    window.location.href = window.location.pathname;
}

/* 2. Инициализация событий */
$(document).ready(function () {
    loadSimpleFilter('/api/regions/', 'dropdown-content-region', 'selected-items-region');
    loadCategories(); // для вложенных категорий
    loadSimpleFilter('/api/pos/', 'dropdown-content-pos', 'selected-items-pos');
    // Кнопки сортировки
    $('.order-button').click(function () {
        $('.order-button').removeClass('active');
        $(this).addClass('active');
        filterWords(getFilters(false));
    });

    // Кнопки фильтров (регионы, части речи, подкатегории)
    $('.filters').on('click', '.filter', function () {
        $(this).toggleClass('active');
        filterWords(getFilters(false));
    });

    // Показать/скрыть блок фильтров
    $('#filters-show').click(function () {
        $('.filters-container').toggleClass('open');
        $(this).toggleClass('active');
    });

    // Поиск по Enter
    $('#word').on('keydown', function (e) {
        if (e.key === 'Enter') {
            filterWords(getFilters(false));
        }
    });

    // Первая загрузка при открытии страницы
    filterWords(getFilters(false));
});
