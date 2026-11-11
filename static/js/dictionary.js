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
 * Формирует словарную статью: заголовок с формами и блок по каждому значению
 * (толкование с отсылками, примеры, граф понятий)
 *
 * @param {Object} word - Структура слова
 * @param {Object[]} word.senses[] - Значения лексемы
 * @param {string[]} word.forms[] - Формы лексемы
 *
 * @returns {Object} DOM-структура - словарная статья
 */
function createWordArticle(word) {
    const article = document.createElement('div');
    article.className = 'word';

    article.appendChild(createWordHeader(word));

    const senses = word.senses || [];
    const numbered = senses.length > 1;
    senses.forEach(sense => {
        article.appendChild(createSenseBlock(word, sense, numbered));
    });

    return article;
}

/**
 * Блок одного значения статьи: толкование, примеры с районами, граф.
 * Нумерация значений показывается, только если их больше одного.
 *
 * @param {Object} word - Структура слова
 * @param {Object} sense - Значение: sense_id, sense_number, meaning,
 *                         references[], examples[{text, region}]
 * @param {boolean} numbered - Показывать ли номер значения
 * @returns {Object} DOM-структура - блок значения
 */
function createSenseBlock(word, sense, numbered) {
    const block = document.createElement('div');
    block.className = 'word-sense';

    const meaning = document.createElement('div');
    meaning.className = 'word-meaning';
    if (numbered) {
        const number = document.createElement('span');
        number.className = 'word-sense-number';
        number.textContent = `${sense.sense_number ?? ''}. `;
        meaning.appendChild(number);
    }
    meaning.appendChild(createMeaningContent(sense));
    block.appendChild(meaning);

    (sense.examples || []).forEach(ex => {
        if (ex.text?.trim()) {
            const example = document.createElement('div');
            example.className = 'word-example';
            example.innerHTML = escapeHtml(ex.text);
            block.appendChild(example);
        }
        if (ex.region?.trim()) {
            const region = document.createElement('div');
            region.className = 'word-region';
            region.textContent = escapeHtml(ex.region);
            block.appendChild(region);
        }
    });

    block.appendChild(createGraphSection(word.word, sense.sense_id));

    return block;
}

/**
 * Текст толкования со ссылками-отсылками («То же, что арап», «уменьш. от …»):
 * целевое слово из references оборачивается в кликабельный span (клик — поиск
 * слова существующим механизмом). Отсылка, не встретившаяся в тексте
 * дословно, выводится отдельной строкой «См.: …».
 *
 * @param {Object} sense - Значение: meaning, references[]
 * @returns {Object} DocumentFragment - толкование со ссылками
 */
function createMeaningContent(sense) {
    const fragment = document.createDocumentFragment();
    const meaning = sense.meaning || '';
    const references = sense.references || [];

    const links = [];
    if (meaning) {
        const { norm, map } = normalizeIndexes(meaning);
        references.forEach(ref => {
            const target = normalizePlain(ref.word);
            const idx = target ? norm.indexOf(target) : -1;
            if (idx === -1) return;
            const start = map[idx];
            const end = map[idx + target.length - 1] + 1;
            if (links.some(l => start < l.end && l.start < end)) return;
            links.push({ start, end, ref });
        });
        links.sort((a, b) => a.start - b.start);

        let cursor = 0;
        links.forEach(link => {
            if (link.start > cursor) {
                fragment.appendChild(document.createTextNode(meaning.slice(cursor, link.start)));
            }
            fragment.appendChild(createRefLink(meaning.slice(link.start, link.end), link.ref));
            cursor = link.end;
        });
        if (cursor < meaning.length) {
            fragment.appendChild(document.createTextNode(meaning.slice(cursor)));
        }
    }

    const missed = references.filter(ref => !links.some(l => l.ref === ref));
    if (missed.length) {
        const box = document.createElement('div');
        box.className = 'word-refs';
        box.append('См.: ');
        missed.forEach((ref, i) => {
            if (i) box.append('; ');
            box.appendChild(createRefLink(ref.accent || ref.word, ref));
        });
        fragment.appendChild(box);
    }

    return fragment;
}

/**
 * Нижний регистр без ударений (комбинируемый акут) — сопоставление слов
 *
 * @param {string} text - исходный текст
 * @returns {string} нормализованный текст
 */
function normalizePlain(text) {
    return (text || '').replace(/\u0301/g, '').toLowerCase();
}

/**
 * Нормализация текста с картой индексов: нормализованный индекс -> исходный.
 * Нужна, чтобы обернуть найденное слово оригинальным фрагментом текста
 * (с ударениями, как в словаре).
 *
 * @param {string} text - исходный текст
 * @returns {Object} {norm: string, map: number[]}
 */
function normalizeIndexes(text) {
    const map = [];
    let norm = '';
    for (let i = 0; i < text.length; i++) {
        if (text[i] === '\u0301') continue;
        norm += text[i].toLowerCase();
        map.push(i);
    }
    return { norm, map };
}

/**
 * Кликабельная отсылка на другое слово: подстановка в строку поиска
 * (тот же механизм, что клик по соседу в графе)
 *
 * @param {string} text - отображаемый текст ссылки
 * @param {Object} ref - отсылка: word (поисковое), accent (для показа)
 * @returns {Object} DOM-элемент ссылки
 */
function createRefLink(text, ref) {
    const link = document.createElement('span');
    link.className = 'word-ref';
    link.textContent = text;
    link.title = 'Перейти к слову';
    link.addEventListener('click', function () {
        $('#word').val(ref.word);
        filterWords(getFilters(false));
    });
    return link;
}

/* 5.1 Граф понятий в карточке */
/**
 * Разворачиваемый раздел графа понятий для одного значения. Ленивая загрузка:
 * граф запрашивается только при первом раскрытии раздела.
 *
 * @param {string} word - лексема карточки
 * @param {number} senseId - id значения (параметр необязательный для API)
 * @returns {Object} DOM-структура - раздел с кнопкой и контейнером графа
 */
function createGraphSection(word, senseId) {
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
            loadGraph(word, senseId, body);
        }
    });

    section.appendChild(toggle);
    section.appendChild(body);
    return section;
}

/**
 * Запрашивает граф понятий значения слова и передаёт контейнер в отрисовку
 *
 * @param {string} word - лексема карточки
 * @param {number} senseId - id значения
 * @param {Object} container - DOM-контейнер под граф
 */
function loadGraph(word, senseId, container) {
    container.textContent = 'Загрузка связей…';
    $.ajax({
        url: '/api/graph/',
        type: 'GET',
        data: { word: word, sense_id: senseId },
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
 * Отрисовывает граф понятий через Cytoscape.js. Начальный вид: слово → его
 * концепты (с числом соседей); соседние лексемы скрыты под концептами —
 * клик по концепту разворачивает/сворачивает его топ-N (полный список
 * живёт в БД). Клик по лексеме-соседу — поиск слова; чипы подкатегорий
 * под графом — поиск по подкатегории; непроверенные узлы — пунктир.
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

    const rootId = `w:${data.word}`;
    const concepts = new Map();  // concept_id -> концепт с топ-N соседями
    const subcats = new Set();

    senses.forEach(sense => {
        sense.subcategories.forEach(name => subcats.add(name));
        sense.concepts.forEach(concept => {
            if (!concepts.has(concept.concept_id)) {
                concepts.set(concept.concept_id, concept);
            }
            concept.neighbors.forEach(n => n.subcategories.forEach(name => subcats.add(name)));
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

    const elements = [{ data: { id: rootId, label: data.word, kind: 'root' } }];
    concepts.forEach(concept => {
        const conceptId = `c:${concept.concept_id}`;
        elements.push({ data: {
            id: conceptId,
            label: `${concept.name} (${concept.neighbors_total})`,
            name: concept.name,
            kind: 'concept',
            unchecked: concept.status === 'unchecked',
            expanded: false,
            neighbors: concept.neighbors,
            neighbors_total: concept.neighbors_total
        } });
        elements.push({ data: {
            id: `e:root-${concept.concept_id}`,
            source: rootId,
            target: conceptId
        } });
    });

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
                    'text-valign': 'center',
                    'text-halign': 'center',
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

    // Клик по концепту — развернуть/свернуть его соседей
    cy.on('tap', 'node[kind = "concept"]', function (event) {
        toggleConcept(cy, event.target);
    });

    // Клик по лексеме-соседу — поиск этого слова
    cy.on('tap', 'node[kind = "neighbor"]', function (event) {
        $('#word').val(event.target.data('word'));
        filterWords(getFilters(false));
    });

    // Наведение: курсор и подсказка со значением
    cy.on('mouseover', 'node', function (event) {
        const node = event.target;
        const kind = node.data('kind');
        canvas.style.cursor = (kind === 'neighbor' || kind === 'concept') ? 'pointer' : 'default';
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
 * Разворачивает или сворачивает соседей концепта (слова с тем же концептом).
 * Сосед, подходящий к двум развёрнутым концептам, остаётся, пока нужен.
 *
 * @param {Object} cy - экземпляр Cytoscape
 * @param {Object} node - узел концепта
 */
function toggleConcept(cy, node) {
    const conceptNodeId = node.id();

    if (node.data('expanded')) {
        const edges = node.connectedEdges().toArray()
            .filter(e => e.data('source') === conceptNodeId);
        const neighborIds = edges.map(e => e.data('target'));
        edges.forEach(e => e.remove());
        neighborIds.forEach(id => {
            const neighbor = cy.getElementById(id);
            if (neighbor.nonempty() && neighbor.connectedEdges().empty()) {
                neighbor.remove();
            }
        });
        node.data('expanded', false);
        node.data('label', `${node.data('name')} (${node.data('neighbors_total')})`);
    } else {
        node.data('neighbors').forEach(n => {
            const neighborId = `w:${n.word}`;
            if (cy.getElementById(neighborId).empty()) {
                cy.add({
                    group: 'nodes',
                    data: {
                        id: neighborId,
                        label: n.accent || n.word,
                        kind: 'neighbor',
                        word: n.word,
                        unchecked: n.status === 'unchecked',
                        tooltip: n.meaning + (n.subcategories.length ? `\n${n.subcategories.join(', ')}` : '')
                    }
                });
            }
            const edgeId = `e:${conceptNodeId}->${neighborId}`;
            if (cy.getElementById(edgeId).empty()) {
                cy.add({
                    group: 'edges',
                    data: { id: edgeId, source: conceptNodeId, target: neighborId }
                });
            }
        });
        node.data('expanded', true);
        node.data('label', node.data('name'));
        runGraphLayout(cy);
    }
}

/**
 * Перераскладка после развёртки концепта (позиции остальных сохраняются)
 */
function runGraphLayout(cy) {
    cy.layout({
        name: 'cose',
        animate: true,
        randomize: false,
        idealEdgeLength: 90,
        nodeRepulsion: 6000
    }).run();
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
 * Формирует заголовок словарной статьи: лексема, формы в скобках
 * (меньшим кеглем), грамматические характеристики
 *
 * @param {Object} word - Структура слова
 * @param {string} word.word - Слово (без ударения).
 * @param {string} word.accent - Слово с ударением.
 * @param {string} word.grammatical_features - часть речи слова
 * @param {Object[]} word.forms[] - формы лексемы: form, accent
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

    const forms = (word.forms || []).map(form => form.accent || form.form);
    const formsSpan = document.createElement('span');
    formsSpan.className = 'word-forms';
    formsSpan.textContent = `(${forms.join('; ')})`;

    const subSpan = document.createElement('span');
    subSpan.className = 'word-subword';
    subSpan.textContent = `${subWord} ${escapeHtml(word.grammatical_features) || ''}`;

    wordDiv.appendChild(mainSpan);
    if (forms.length) {
        wordDiv.appendChild(formsSpan);
    }
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
 * Один элемент результата = одна статья (заголовок + блоки значений).
 *
 * @param {Object[]} words - Массив объектов слов от сервера.
 * @param {string} words[].word - Слово (без ударения).
 * @param {string} words[].accent - Слово с ударением.
 * @param {Object[]} words[].senses - Значения лексемы.
 * @param {Object[]} words[].forms - Формы лексемы.
 */
function renderResults(words) {
    const container = document.getElementById('words');
    container.innerHTML = '';

    if (!words || words.length === 0) {
        container.innerHTML = '<p style="padding: 20px;">Ничего не найдено. Попробуйте другой запрос.</p>';
        return;
    }

    words.forEach(w => container.appendChild(createWordArticle(w)));
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
