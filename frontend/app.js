// --- СОСТОЯНИЕ ПРИЛОЖЕНИЯ ---
let chats = [];
let activeChatId = null;
let isGenerating = false;

// --- DOM ЭЛЕМЕНТЫ ---
const chatList = document.getElementById('chat-list');
const newChatBtn = document.getElementById('new-chat-btn');
const messagesContainer = document.getElementById('messages-container');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const welcomeScreen = document.getElementById('welcome-screen');
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const activeChatTitle = document.getElementById('active-chat-title');
const chatHeaderMeta = document.getElementById('chat-header-meta');

// --- ИНИЦИАЛИЗАЦИЯ ---
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupEventListeners();
});

async function initApp() {
    await checkBackendStatus();
    await loadChats();
    
    // Автоматическая проверка статуса сервера каждые 15 секунд
    setInterval(checkBackendStatus, 15000);
}

// --- СВЯЗЬ С API ---

async function checkBackendStatus() {
    try {
        const response = await fetch('/api/health');
        if (response.ok) {
            const data = await response.json();
            statusIndicator.className = 'status-indicator online';
            if (data.llm_mode === 'mock') {
                statusText.textContent = 'Работает (Режим теста)';
            } else {
                statusText.textContent = 'Онлайн (CPU)';
            }
            enableInput(true);
        } else {
            throw new Error();
        }
    } catch (e) {
        statusIndicator.className = 'status-indicator offline';
        statusText.textContent = 'Сервер оффлайн';
        enableInput(false);
    }
}

async function loadChats() {
    try {
        const response = await fetch('/api/chats');
        if (response.ok) {
            chats = await response.json();
            renderChatList();
        }
    } catch (e) {
        console.error('Ошибка загрузки списка чатов:', e);
    }
}

async function createNewChat(title = "Новый чат") {
    try {
        const response = await fetch('/api/chats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
        if (response.ok) {
            const newChat = await response.json();
            chats.unshift(newChat);
            renderChatList();
            await selectChat(newChat.id);
            chatInput.focus();
        }
    } catch (e) {
        console.error('Ошибка создания чата:', e);
    }
}

async function deleteChat(chatId, event) {
    if (event) event.stopPropagation(); // Исключаем клик по самому чату
    
    if (!confirm('Вы уверены, что хотите удалить этот чат?')) return;
    
    try {
        const response = await fetch(`/api/chats/${chatId}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            chats = chats.filter(c => c.id !== chatId);
            renderChatList();
            
            if (activeChatId === chatId) {
                activeChatId = null;
                showWelcomeScreen();
            }
        }
    } catch (e) {
        console.error('Ошибка удаления чата:', e);
    }
}

async function selectChat(chatId) {
    activeChatId = chatId;
    
    // Подсвечиваем активный чат в списке
    document.querySelectorAll('.chat-item').forEach(item => {
        if (item.dataset.id === chatId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    const activeChat = chats.find(c => c.id === chatId);
    if (activeChat) {
        activeChatTitle.textContent = activeChat.title;
        chatHeaderMeta.style.display = 'flex';
    }

    welcomeScreen.style.display = 'none';
    messagesContainer.innerHTML = '';
    
    // Показываем индикатор загрузки сообщений
    showMessagesLoading(true);

    try {
        const response = await fetch(`/api/chats/${chatId}/messages`);
        showMessagesLoading(false);
        if (response.ok) {
            const messages = await response.json();
            if (messages.length === 0) {
                showEmptyChatWelcome();
            } else {
                messages.forEach(msg => {
                    renderMessage(msg.role, msg.content);
                });
                scrollToBottom();
            }
        }
    } catch (e) {
        showMessagesLoading(false);
        console.error('Ошибка получения сообщений:', e);
    }
}

// --- РЕНДЕРИНГ ЭЛЕМЕНТОВ ---

function renderChatList() {
    chatList.innerHTML = '';
    
    if (chats.length === 0) {
        chatList.innerHTML = '<div class="input-footer" style="padding: 10px; text-align: center;">Нет сохраненных диалогов.</div>';
        return;
    }

    chats.forEach(chat => {
        const chatItem = document.createElement('div');
        chatItem.className = `chat-item ${chat.id === activeChatId ? 'active' : ''}`;
        chatItem.dataset.id = chat.id;
        chatItem.onclick = () => selectChat(chat.id);

        chatItem.innerHTML = `
            <div class="chat-item-info">
                <span class="chat-item-icon">💬</span>
                <span class="chat-item-title" title="${chat.title}">${escapeHTML(chat.title)}</span>
            </div>
            <button class="chat-delete-btn" onclick="deleteChat('${chat.id}', event)" title="Удалить чат">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    <line x1="10" y1="11" x2="10" y2="17"></line>
                    <line x1="14" y1="11" x2="14" y2="17"></line>
                </svg>
            </button>
        `;
        chatList.appendChild(chatItem);
    });
}

function renderMessage(role, content, messageId = null) {
    const isUser = role === 'user';
    const row = document.createElement('div');
    row.className = `message-row ${isUser ? 'user' : 'assistant'}`;
    if (messageId) row.id = messageId;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    if (isUser) {
        bubble.textContent = content;
        row.appendChild(bubble);
    } else {
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = '⚡';
        
        bubble.innerHTML = formatMarkdown(content);
        
        row.appendChild(avatar);
        row.appendChild(bubble);
    }

    messagesContainer.appendChild(row);
    return bubble;
}

// --- ОТПРАВКА СООБЩЕНИЯ И SSE СТРИМИНГ ---

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text || isGenerating || !activeChatId) return;

    chatInput.value = '';
    adjustInputHeight();
    
    // Блокируем ввод на время генерации
    setGeneratingState(true);

    // Удаляем пустой приветственный текст если он есть
    const emptyWelcome = document.getElementById('empty-chat-welcome');
    if (emptyWelcome) emptyWelcome.remove();

    // 1. Рендерим сообщение пользователя
    renderMessage('user', text);
    scrollToBottom();

    // 2. Рендерим заглушку сообщения ассистента с индикатором печати
    const assistantBubble = renderMessage('assistant', '');
    const typingIndicator = showTypingIndicator(assistantBubble);
    scrollToBottom();

    let accumulatedResponse = '';

    try {
        // Открываем POST запрос для отправки сообщения.
        // Ответ будет стримиться чанками по HTTP в режиме EventStream.
        const response = await fetch(`/api/chats/${activeChatId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: text })
        });

        if (!response.ok) {
            throw new Error('Ошибка связи с бэкендом');
        }

        // Убираем индикатор печати и начинаем стрим текста
        typingIndicator.remove();

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            
            // Оставляем последний незавершенный элемент в буфере
            buffer = lines.pop();

            for (const line of lines) {
                const cleanLine = line.trim();
                if (!cleanLine) continue;
                
                if (cleanLine.startsWith('data: ')) {
                    const dataStr = cleanLine.substring(6);
                    if (dataStr === '[DONE]') {
                        break;
                    }
                    
                    try {
                        const data = JSON.parse(dataStr);
                        if (data.error) {
                            renderError(assistantBubble, data.error);
                            break;
                        }
                        if (data.content) {
                            accumulatedResponse += data.content;
                            assistantBubble.innerHTML = formatMarkdown(accumulatedResponse);
                            scrollToBottom();
                        }
                    } catch (e) {
                        console.warn('Ошибка декодирования JSON из стрима:', e, cleanLine);
                    }
                }
            }
        }
        
        // После завершения генерации перезапрашиваем чаты (чтобы обновить заголовки чатов)
        await loadChats();
        // Убедимся, что активный чат подсвечен правильно
        document.querySelectorAll('.chat-item').forEach(item => {
            if (item.dataset.id === activeChatId) {
                item.classList.add('active');
            }
        });

    } catch (error) {
        console.error('Ошибка стриминга:', error);
        typingIndicator.remove();
        renderError(assistantBubble, 'Не удалось сгенерировать ответ. Пожалуйста, проверьте подключение к серверу.');
    } finally {
        setGeneratingState(false);
        chatInput.focus();
    }
}

// --- УТИЛИТЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

function showWelcomeScreen() {
    welcomeScreen.style.display = 'flex';
    activeChatTitle.textContent = 'Выберите диалог или создайте новый';
    chatHeaderMeta.style.display = 'none';
    messagesContainer.innerHTML = '';
}

function showEmptyChatWelcome() {
    const welcome = document.createElement('div');
    welcome.id = 'empty-chat-welcome';
    welcome.className = 'welcome-screen';
    welcome.innerHTML = `
        <div class="welcome-card" style="max-width: 500px; padding: 30px;">
            <div class="welcome-logo" style="width: 44px; height: 44px; font-size: 22px; margin-bottom: 16px;">⚡</div>
            <h3 style="margin-bottom: 8px;">Новый диалог открыт</h3>
            <p style="font-size: 13.5px; margin-bottom: 0;">Спросите меня о финансовой группе Сентрас. Я готов ответить строго по фактам.</p>
        </div>
    `;
    messagesContainer.appendChild(welcome);
}

function showMessagesLoading(show) {
    if (show) {
        const loader = document.createElement('div');
        loader.id = 'messages-loader';
        loader.className = 'chat-list-skeleton';
        loader.style.width = '200px';
        loader.style.margin = '20px auto';
        loader.innerHTML = `
            <div class="skeleton-item"></div>
            <div class="skeleton-item" style="animation-delay: 0.2s"></div>
        `;
        messagesContainer.appendChild(loader);
    } else {
        const loader = document.getElementById('messages-loader');
        if (loader) loader.remove();
    }
}

function showTypingIndicator(container) {
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    container.appendChild(indicator);
    return indicator;
}

function renderError(container, message) {
    container.innerHTML = `
        <div class="error-bubble">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>${escapeHTML(message)}</span>
        </div>
    `;
}

function setGeneratingState(generating) {
    isGenerating = generating;
    sendBtn.disabled = generating || !activeChatId;
    chatInput.disabled = generating || !activeChatId;
    if (generating) {
        sendBtn.innerHTML = `
            <svg class="spinner" width="18" height="18" viewBox="0 0 50 50" style="animation: rotate 2s linear infinite;">
                <circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="80, 200" stroke-dashoffset="0" stroke-linecap="round" style="animation: dash 1.5s ease-in-out infinite;"></circle>
            </svg>
        `;
    } else {
        sendBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
        `;
    }
}

function enableInput(enabled) {
    if (!activeChatId) {
        chatInput.disabled = true;
        sendBtn.disabled = true;
        chatInput.placeholder = 'Создайте новый чат для начала общения';
    } else {
        chatInput.disabled = !enabled || isGenerating;
        sendBtn.disabled = !enabled || isGenerating;
        chatInput.placeholder = 'Напишите сообщение о группе Сентрас...';
    }
}

function adjustInputHeight() {
    chatInput.style.height = 'auto';
    chatInput.style.height = (chatInput.scrollHeight) + 'px';
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Форматирование Markdown в HTML
function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHTML(text);

    // Замена переносов строк на <br>
    html = html.replace(/\n/g, '<br>');

    // Жирный текст **bold** -> <strong>bold</strong>
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Курсив *italic* -> <em>italic</em>
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Однострочный код `code` -> <code>code</code>
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');

    // Списки (маркированные): строки, начинающиеся с "- " или "* "
    // Разделяем по <br> и форматируем
    const lines = html.split('<br>');
    let inList = false;
    const formattedLines = [];

    for (let line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            const listContent = trimmed.substring(2);
            if (!inList) {
                formattedLines.push('<ul>');
                inList = true;
            }
            formattedLines.push(`<li>${listContent}</li>`);
        } else {
            if (inList) {
                formattedLines.push('</ul>');
                inList = false;
            }
            formattedLines.push(line);
        }
    }
    if (inList) {
        formattedLines.push('</ul>');
    }

    return formattedLines.join('<br>').replace(/<\/ul><br>/g, '</ul>').replace(/<br><ul>/g, '<ul>');
}

function escapeHTML(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// --- СЛУШАТЕЛИ СОБЫТИЙ ---

function setupEventListeners() {
    // Кнопка нового чата
    newChatBtn.onclick = () => createNewChat();

    // Отправка по кнопке
    sendBtn.onclick = sendMessage;

    // Ввод текста (автовысота и отправка по Enter)
    chatInput.oninput = adjustInputHeight;
    chatInput.onkeydown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    // Клик по карточкам-подсказкам на стартовом экране
    document.querySelectorAll('.suggestion-card').forEach(card => {
        card.onclick = async () => {
            const prompt = card.dataset.prompt;
            await createNewChat(prompt.length > 30 ? prompt.substring(0, 27) + '...' : prompt);
            chatInput.value = prompt;
            await sendMessage();
        };
    });
}

// CSS стили спиннера (добавлены динамически)
const style = document.createElement('style');
style.textContent = `
@keyframes rotate { 100% { transform: rotate(360deg); } }
@keyframes dash {
  0% { stroke-dasharray: 1, 200; stroke-dashoffset: 0; }
  50% { stroke-dasharray: 89, 200; stroke-dashoffset: -35px; }
  100% { stroke-dasharray: 89, 200; stroke-dashoffset: -124px; }
}
`;
document.head.appendChild(style);
