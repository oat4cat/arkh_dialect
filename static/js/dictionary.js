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


/* Загружаем простые фильтры (без вложенности) */
function loadSimpleFilter(apiUrl, containerId, selectedContainerId) {
    $.ajax({
        url: apiUrl,
        type: 'GET',
        success: function (data) {
            const container = $(`#${containerId}`);
            container.empty();

            data.forEach(item => {
                const value = item.name || item; // name для регионов, строка для pos
                const label = item.name || item;

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

/* Загружаем категории с подкатегориями */
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

/* Показываем выбранные теги */
function createSelectedTag(label, value) {
    const tag = document.createElement('div');
    tag.className = 'selected-item';
    tag.setAttribute('data', value);
    tag.innerHTML = `
        ${label}
        <span class="remove" onclick="removeFilter(this, '${value}')">×</span>
    `;
    return tag;
}

/* Удаляем фильтр из списка выбранных */
function removeFilter(element, value) {
    // Находим и удаляем кнопку фильтра в дропдауне
    $(`.filter[data="${value}"]`).removeClass('active');

    // Удаляем тег
    $(element).parent().remove();
    filterWords(getFilters(false));
}

/* 3. Сбор текущих параметров фильтрации */
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
function createWordArticle(wordData) {
    const article = document.createElement('div');
    article.className = 'word';

    const header = createWordHeader(wordData);
    article.appendChild(header);

    if (wordData.meaning) {
        const meaning = document.createElement('div');
        meaning.className = 'word-meaning';
        meaning.innerHTML = escapeHtml(wordData.meaning);
        article.appendChild(meaning);
    }

    wordData.examples.forEach(ex => {
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

    return article;
}

function createWordHeader(w) {
    const header = document.createElement('div');
    header.className = 'word-header';

    const wordDiv = document.createElement('div');
    wordDiv.className = 'word-word';

    const parts = (w.accent || '').trim().split(/\s+/);
    const mainWord = parts[0] || w.word;
    const subWord = parts.slice(1).join(' ');

    const mainSpan = document.createElement('span');
    mainSpan.textContent = mainWord;

    const subSpan = document.createElement('span');
    subSpan.className = 'word-subword';
    subSpan.textContent = `${subWord} ${escapeHtml(w.grammatical_features) || ''}`;

    wordDiv.appendChild(mainSpan);
    wordDiv.appendChild(subSpan);

    const categoryDiv = document.createElement('div');
    categoryDiv.className = 'word-category';
    categoryDiv.textContent = escapeHtml(w.subcategories.join(', ') || '');

    header.appendChild(wordDiv);
    header.appendChild(categoryDiv);

    return header;
}

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
        const cls = isActive ? 'disabled' : '';
        const onclick = isActive ? '' : `onclick="pagination(this)"`;
        html += `<li class="page-item ${cls}" data-page="${pageNum}" ${onclick}><span class="page-link">${pageNum}</span></li>`;
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
    $('.footer .pagination-row, .footer .to_page').remove();
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

    $('.footer').prepend(html);
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
