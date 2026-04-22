const found_items = new Set();
const selectedItems = new Set();
let regions_map = {}
let markers = [];

const regionCenters = {
    'velsk': { x: 430.050, y: 802.705 },
    'verhnetoem': { x: 661.187, y: 643.540 },
    'vileg': { x: 842.209, y: 824.457 },
    'vinogr': { x: 517.969, y: 575.402 },
    'kargop': { x: 200.585, y: 786.200 },
    //'kenozero': { x: 380, y: 290 },
    'konosh': { x: 295.121, y: 850.691 },
    'kotlas': { x: 744.699, y: 810.780 },
    'krasnob': { x: 724.85, y: 734.88 },
    'lensk': { x: 871.138, y: 702.714 },
    'leshuk': { x: 785.527, y: 277.093 },
    'mezen': { x: 609.258, y: 123.991 },
    'nyandom': { x: 319.071, y: 718.251 },
    'nao': { x: 1247.166, y: -258.140 },
    'onezh': { x: 140.240, y: 455.776 },
    'pinezh': { x: 573.765, y: 385.540 },
    'plesec': { x: 269.293, y: 607.585 },
    'primor': { x: 261.436, y: 285.130 },
    'ustian': { x: 555.433, y: 814.22 },
    'holm': { x: 412.678, y: 428.484 },
    'shenk': { x: 455.979, y: 691.742 }
};

/**
 * Скрывает первоначальную инструкцию, ищет выбранное слово
 */
function searchItems() {
    $('.prolog').hide();
    const searchTerm = document.getElementById('word').value;
    fetch(`/api/map/?search=${encodeURIComponent(searchTerm)}`)
        .then(response => response.json())
        .then(data => {
            found_items.clear();
            data.forEach(item => {
                found_items.add(item)
            });
            fillDropdown('-map', found_items)
            showDropdown('-map');
        })
        .catch(error => console.error('Error:', error));
}

function fillDropdown(label, data) {
    const dropdownContent = document.getElementById('dropdown-content' + label);
    remembered_word = '';
    data.forEach(item => {
        if (item.word != remembered_word) {
            remembered_word = item.word;
            const itemElement = document.createElement('div');
            itemElement.classList.add('option');
            itemElement.onclick = (event) => selectOption(item.word, '-map');
            itemElement.innerHTML = `${item.word}`;
            dropdownContent.appendChild(itemElement);

        }

    });
}


function showDropdown(label) {
    const dropdownContent = document.getElementById('dropdown-content' + label);
    dropdownContent.style.display = 'block';
}

function hideDropdown(label) {
    const dropdownContents = document.getElementById('dropdown-content' + label);
    dropdownContents.style.display = 'none';
    dropdownContents.innerHTML = '';
}


function selectOption(word, label) {
    const filterInput = document.getElementById('filter-input' + label);
    let selectedItemsContainer = document.getElementById('selected-items' + label);

    found_items.forEach(item => {
        if (item.word == word) {
            selectedItems.add(item);
        }
    });

    // не аппендим, а заново перерисовываем и карту, и контейнер для слов
    addItems(selectedItems, selectedItemsContainer);

    hideDropdown('-map');
}

function addItems(data, container) {
    container.innerHTML = '';
    counter = 0;
    remembered_word = '';
    data.forEach(item => {
        if (item.word != remembered_word) {
            counter += 1;
            remembered_word = item.word;
        }
        item['index'] = counter;
    });
    counter = 0;
    data.forEach(item => {
        if (item.index != counter) {
            counter += 1;
            const itemElement = document.createElement('div');
            itemElement.classList.add('selected-item');
            itemElement.innerHTML = `<span class="number">${item.index}</span> ${item.word} <span class="remove" onclick="removeSelectedItem('${item.word}', '${item.index}', this.parentElement.parentElement)">×</span>`;
            container.appendChild(itemElement);
        }

    });
    clearMap();
    placeMarkers(data);
}


function removeSelectedItem(word, index, container) {
    const itemElements = container.querySelectorAll('.selected-item');
    itemElements.forEach(element => {
        if (element.textContent.includes(index + ' ' + word)) {
            element.remove();
        }

    });
    selectedItems.forEach(item => {
        if (item.word == word && item.index == index) {
            selectedItems.delete(item);
        }
    });
    // перерисовываем карту
    clearMap();
    placeMarkers(selectedItems);
}

document.addEventListener('click', function (event) {
    if (!event.target.matches('#dropdown-content' + '-map')) {
        hideDropdown('-map');
    }
});

function placeMarkers(data) {
    const map = document.getElementById('map');

    // Группируем по регионам
    data.forEach(item => {
        if (!regions_map[item.region]) {
            regions_map[item.region] = [];
        }
        const existingItem = regions_map[item.region].find(existing => existing.index === item.index);
        if (!existingItem) {
            regions_map[item.region].push(item);
        }
    });

    // Для каждого региона размещаем маркеры
    for (const region in regions_map) {
        const path = document.getElementById(region_short_to_en[region]);
        if (!path) continue;

        const regionKey = region_short_to_en[region];
        let center = regionCenters[regionKey];
        if (!center) {
            // Fallback: вычисляем динамически
            center = getRegionCenter(path);
        }


        const items = regions_map[region];
        const radius = calculateRadius(items.length, path); // Адаптивный радиус

        items.forEach((item, index) => {
            let x, y;

            if (items.length === 1) {
                // Один маркер - точно в центр
                x = center.x;
                y = center.y;
            } else {
                // Несколько маркеров - размещаем по кругу
                const angle = (2 * Math.PI / items.length) * index;
                // Смещаем в зависимости от количества маркеров
                const actualRadius = radius + (index * 5); // Немного увеличиваем радиус для каждого
                x = center.x + actualRadius * Math.cos(angle);
                y = center.y + actualRadius * Math.sin(angle);
            }

            addMarker(x, y, item.index, `${item.accent} (${item.region})`);
        });
    }
}

// Функция для нахождения настоящего центра пути
function getRegionCenter(path) {
    try {
        // Получаем bounding box
        const bbox = path.getBBox();

        // Если путь очень вытянутый, используем weighted center
        // Для сложных форм можно использовать sampling точек пути
        let totalX = 0, totalY = 0, points = 0;

        // Пробуем получить точки пути
        if (path.getPointAtLength) {
            const length = path.getTotalLength();
            const step = Math.min(length / 50, 50); // Максимум 50 точек для производительности

            for (let i = 0; i <= length; i += step) {
                const point = path.getPointAtLength(i);
                totalX += point.x;
                totalY += point.y;
                points++;
            }

            if (points > 0) {
                return {
                    x: totalX / points,
                    y: totalY / points
                };
            }
        }

        // Fallback: используем центр bounding box
        return {
            x: bbox.x + bbox.width / 2,
            y: bbox.y + bbox.height / 2
        };
    } catch (e) {
        console.error('Error getting region center:', e);
        const bbox = path.getBBox();
        return {
            x: bbox.x + bbox.width / 2,
            y: bbox.y + bbox.height / 2
        };
    }
}

// Функция для расчёта радиуса размещения маркеров
function calculateRadius(markerCount, path) {
    const bbox = path.getBBox();
    const regionSize = Math.min(bbox.width, bbox.height);

    // Адаптивный радиус: зависит от размера региона и количества маркеров
    let radius = Math.min(regionSize * 0.15, 60); // Не более 60px

    if (markerCount > 5) {
        radius = radius * 1.5; // Больше маркеров - больше радиус
    } else if (markerCount < 3) {
        radius = radius * 0.8; // Мало маркеров - компактнее
    }

    return Math.max(radius, 25); // Минимум 25px
}

function addMarker(svgX, svgY, index, name) {
    const svg = document.getElementById('map');
    const rect = svg.getBoundingClientRect();
    const vb = svg.getAttribute('viewBox').split(' ').map(Number);

    const scaleX = rect.width / vb[2];
    const scaleY = rect.height / vb[3];

    const left = (svgX - vb[0]) * scaleX;
    const top = (svgY - vb[1]) * scaleY;

    const marker = document.createElement('div');
    marker.className = 'marker';
    marker.style.left = `${left}px`;
    marker.style.top = `${top}px`;
    marker.innerHTML = index;
    marker.title = name;

    // Сохраняем исходные SVG-координаты для пересчёта при ресайзе
    marker.dataset.svgX = svgX;
    marker.dataset.svgY = svgY;

    document.querySelector('.map').appendChild(marker);
    markers.push(marker);
}

function recalculateMarkers() {
    const svg = document.getElementById('map');
    const rect = svg.getBoundingClientRect();
    const vb = svg.getAttribute('viewBox').split(' ').map(Number);
    const scaleX = rect.width / vb[2];
    const scaleY = rect.height / vb[3];

    markers.forEach(marker => {
        const svgX = parseFloat(marker.dataset.svgX);
        const svgY = parseFloat(marker.dataset.svgY);
        marker.style.left = ((svgX - vb[0]) * scaleX) + 'px';
        marker.style.top = ((svgY - vb[1]) * scaleY) + 'px';
    });
}

function clearMap() {
    markers.forEach(marker => marker.remove());
    markers = [];
}



document.querySelectorAll('path').forEach(path => {
    path.addEventListener('mouseenter', function (event) {
        const regionId = event.target.id;
        const regionInfo = regions_map[Object.keys(region_short_to_en).find(key => region_short_to_en[key] === regionId)];
        if (regionInfo) {
            showRegionDropdown(regionInfo, regionId, event);
        } else {
            showRegionDropdown('', regionId, event);
        }
    });
    path.addEventListener('mouseleave', function (event) {
        hideRegionDropdown();
    });
});

function showRegionDropdown(regionInfo, regionId, event) {
    hideRegionDropdown();
    const dropdown = document.getElementById('dropdown_region');
    const regionName = document.getElementById('region-name');
    const regionWords = document.getElementById('region-words');

    regionName.textContent = region_en_to_full[regionId];

    regionWords.innerHTML = '';
    if (regionInfo === '') {
        const li = document.createElement('li');
        li.textContent = '';
        regionWords.appendChild(li);
    }
    else {
        regionInfo.forEach(word => {
            const li = document.createElement('li');
            li.innerHTML = `<span class="word_index">${escapeHtml(word.index.toString())}</span> &ndash; <span class="word">${escapeHtml(word.accent)}</span>, <span class="grammar">${escapeHtml(word.grammatical_features)}</span> <span class="meaning">${escapeHtml(word.meaning)}</span>`;
            regionWords.appendChild(li);
        });
    }
    const mapRect = document.querySelector('.map').getBoundingClientRect();
    const dropdownWidth = 350; // Примерная ширина
    const dropdownHeight = 200; // Примерная высота

    // Координаты мыши ОТНОСИТЕЛЬНО контейнера карты
    let left = event.clientX - mapRect.left + 20;
    let top = event.clientY - mapRect.top + 20;

    // Проверяем границы ОКНА 
    if (left + dropdownWidth > window.innerWidth) {
        left = window.innerWidth - dropdownWidth - 10;
    }
    if (top + dropdownHeight > window.innerHeight) {
        top = window.innerHeight - dropdownHeight - 10;
    }

    // Применяем координаты (fixed positioning)
    dropdown.style.left = `${left}px`;
    dropdown.style.top = `${top}px`;
    dropdown.classList.add('visible');
}

function hideRegionDropdown() {
    const dropdown = document.getElementById('dropdown_region');
    dropdown.classList.remove('visible');
}


$(document).ready(function () {

    // Поиск по Enter
    $('#word').on('keydown', function (e) {
        if (e.key === 'Enter') {
            searchItems();
        }
    });

});

window.addEventListener('resize', recalculateMarkers);
