<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>AWESOME AI 2026</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg-primary: #0d0d12;
            --bg-secondary: #16161e;
            --bg-chat: #1c1c26;
            --bg-input: #252530;
            --bg-hover: #2d2d3a;
            --text-primary: #ececf1;
            --text-secondary: #a1a1aa;
            --text-muted: #6b6b7a;
            --accent: #7c5cfc;
            --accent-glow: rgba(124, 92, 252, 0.2);
            --border: #2a2a36;
            --radius: 12px;
            --shadow: 0 8px 32px rgba(0,0,0,0.6);
            --transition: all 0.2s ease;
        }
        html, body { height: 100%; font-family: 'Inter', sans-serif; background: var(--bg-primary); color: var(--text-primary); overflow: hidden; -webkit-font-smoothing: antialiased; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 10px; }

        #app { display: flex; height: 100vh; width: 100vw; background: var(--bg-primary); overflow: hidden; }
        #sidebar {
            width: 260px; min-width: 260px; background: var(--bg-secondary); border-right: 1px solid var(--border);
            display: flex; flex-direction: column; padding: 14px 12px; height: 100vh; overflow-y: auto; flex-shrink: 0;
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); z-index: 100;
        }
        #sidebar .logo { display: flex; align-items: center; gap: 10px; padding: 6px 4px 18px 4px; font-weight: 700; font-size: 17px; color: var(--text-primary); }
        #sidebar .logo .badge { background: var(--accent); color: #fff; font-size: 9px; font-weight: 600; padding: 2px 10px; border-radius: 20px; box-shadow: 0 0 20px var(--accent-glow); text-transform: uppercase; }
        .new-chat-btn {
            background: var(--accent); color: #fff; border: none; border-radius: var(--radius); padding: 11px 16px;
            font-weight: 600; font-size: 14px; cursor: pointer; transition: var(--transition);
            display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; margin-bottom: 14px;
            box-shadow: 0 0 24px var(--accent-glow);
        }
        .new-chat-btn:hover { transform: scale(1.02); box-shadow: 0 0 36px var(--accent-glow); }
        .new-chat-btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
        .history-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 6px 6px 6px; }
        .history-list { flex: 1; overflow-y: auto; margin-top: 4px; }
        .history-item {
            padding: 9px 12px; border-radius: 10px; cursor: pointer; transition: var(--transition);
            color: var(--text-secondary); font-size: 13.5px; display: flex; align-items: center; gap: 10px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px;
        }
        .history-item:hover, .history-item.active { background: var(--bg-hover); color: var(--text-primary); }
        .history-item .icon { opacity: 0.5; font-size: 14px; flex-shrink: 0; }
        .sidebar-footer {
            border-top: 1px solid var(--border); padding-top: 12px; margin-top: 8px;
            font-size: 12px; color: var(--text-muted); display: flex; flex-direction: column; gap: 6px;
        }
        .sidebar-footer .user-row { display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 8px; cursor: pointer; transition: var(--transition); }
        .sidebar-footer .user-row:hover { background: var(--bg-hover); }
        .sidebar-footer .avatar { width: 28px; height: 28px; border-radius: 50%; background: var(--accent); display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 12px; color: #fff; flex-shrink: 0; }
        .sidebar-footer .status-dot { width: 6px; height: 6px; border-radius: 50%; background: #22c55e; display: inline-block; margin-left: auto; }

        #main { flex: 1; display: flex; flex-direction: column; background: var(--bg-primary); height: 100vh; overflow: hidden; }
        #chat-header {
            padding: 14px 24px; border-bottom: 1px solid var(--border);
            display: flex; align-items: center; justify-content: space-between;
            background: var(--bg-primary); flex-shrink: 0; min-height: 56px;
        }
        #chat-header .title { font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 10px; }
        #chat-header .title .status { font-size: 11px; font-weight: 400; color: var(--text-muted); }
        #chat-header .title .status.online { color: #22c55e; }
        .header-actions button { background: transparent; border: none; color: var(--text-secondary); cursor: pointer; padding: 6px 10px; border-radius: 8px; transition: var(--transition); font-size: 13px; }
        .header-actions button:hover { background: var(--bg-hover); color: var(--text-primary); }

        #messages {
            flex: 1; overflow-y: auto; padding: 20px 24px 12px 24px;
            display: flex; flex-direction: column; gap: 4px; scroll-behavior: smooth;
        }
        .msg {
            display: flex; gap: 12px; padding: 10px 14px; border-radius: var(--radius);
            max-width: 85%; animation: msgIn 0.25s ease; line-height: 1.6; font-size: 14.5px;
        }
        @keyframes msgIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .msg.user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 4px; }
        .msg.bot { align-self: flex-start; background: var(--bg-chat); color: var(--text-primary); border-bottom-left-radius: 4px; }
        .msg .avatar { width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 14px; background: var(--bg-hover); }
        .msg.user .avatar { background: var(--accent); color: #fff; }
        .msg .content { word-break: break-word; white-space: pre-wrap; }
        .msg .content .time { font-size: 10px; opacity: 0.5; margin-left: 10px; font-weight: 400; }
        .msg .content a { color: #8b7cfc; text-decoration: none; }
        .msg .content a:hover { text-decoration: underline; }
        .msg .content code { background: rgba(255,255,255,0.08); padding: 1px 6px; border-radius: 4px; font-size: 13px; }
        .msg .content pre { background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; overflow-x: auto; font-size: 13px; margin: 4px 0; }

        .typing-indicator {
            display: none; align-self: flex-start; padding: 10px 16px;
            background: var(--bg-chat); border-radius: var(--radius); border-bottom-left-radius: 4px;
            gap: 4px; margin-top: 4px;
        }
        .typing-indicator span { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); animation: typing 1.2s infinite; }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes typing { 0%,60%,100% { transform: translateY(0); opacity: 0.3; } 30% { transform: translateY(-6px); opacity: 1; } }

        #input-area {
            padding: 12px 24px 20px 24px; border-top: 1px solid var(--border);
            background: var(--bg-primary); flex-shrink: 0; display: flex; gap: 10px; align-items: flex-end;
        }
        #input-area textarea {
            flex: 1; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius);
            padding: 10px 14px; color: var(--text-primary); font-family: inherit; font-size: 14px;
            resize: none; outline: none; transition: var(--transition); min-height: 44px; max-height: 160px; line-height: 1.5;
        }
        #input-area textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        #input-area textarea::placeholder { color: var(--text-muted); }
        #input-area .send-btn {
            background: var(--accent); color: #fff; border: none; border-radius: var(--radius);
            padding: 10px 16px; cursor: pointer; transition: var(--transition); font-size: 16px;
            min-height: 44px; display: flex; align-items: center; justify-content: center;
            box-shadow: 0 0 20px var(--accent-glow);
        }
        #input-area .send-btn:hover { transform: scale(1.04); box-shadow: 0 0 30px var(--accent-glow); }
        #input-area .send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        #sidebar-toggle { display: none; background: transparent; border: none; color: var(--text-secondary); font-size: 22px; cursor: pointer; padding: 4px 8px; }
        #sidebar-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 99; backdrop-filter: blur(4px); }

        @media (max-width: 768px) {
            #sidebar { position: fixed; top: 0; left: 0; height: 100vh; transform: translateX(-100%); width: 280px; z-index: 101; border-right: 1px solid var(--border); box-shadow: 4px 0 40px rgba(0,0,0,0.5); }
            #sidebar.open { transform: translateX(0); }
            #sidebar-overlay.active { display: block; }
            #sidebar-toggle { display: block; }
            #chat-header .title { font-size: 14px; }
            #messages { padding: 14px 16px 8px 16px; }
            #input-area { padding: 10px 16px 16px 16px; }
            .msg { max-width: 92%; font-size: 14px; padding: 8px 12px; }
        }
        @media (max-width: 480px) {
            #chat-header { padding: 10px 12px; }
            #messages { padding: 10px 10px 6px 10px; }
            #input-area { padding: 8px 10px 12px 10px; gap: 6px; }
            #input-area textarea { font-size: 13px; padding: 8px 10px; min-height: 36px; }
            .msg { max-width: 95%; font-size: 13px; padding: 6px 10px; }
            .msg .avatar { width: 22px; height: 22px; font-size: 11px; }
        }
    </style>
</head>
<body>
<div id="app">
    <div id="sidebar-overlay"></div>
    <aside id="sidebar">
        <div class="logo"><span>🧠</span> AWESOME AI <span class="badge">2026</span></div>
        <button class="new-chat-btn" onclick="newChat()">
            <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg> Новый чат
        </button>
        <div class="history-label">История</div>
        <div class="history-list" id="historyList"></div>
        <div class="sidebar-footer">
            <div class="user-row" id="userRow">
                <div class="avatar" id="userAvatar">👤</div>
                <span id="userName">Гость</span>
                <span class="status-dot"></span>
            </div>
            <div style="display:flex;gap:10px;padding:4px 8px;font-size:12px;color:var(--text-muted);">
                <span id="userStatus">🔓 Бесплатный</span>
                <span id="userLimit">20/день</span>
            </div>
        </div>
    </aside>

    <main id="main">
        <header id="chat-header">
            <div style="display:flex;align-items:center;gap:8px;">
                <button id="sidebar-toggle" onclick="toggleSidebar()">☰</button>
                <div class="title">AWESOME AI <span class="status online">● Онлайн</span></div>
            </div>
            <div class="header-actions">
                <button onclick="newChat()" title="Новый чат">✦</button>
                <button onclick="clearChat()" title="Очистить">🗑</button>
            </div>
        </header>

        <div id="messages">
            <div class="msg bot">
                <div class="avatar">🧠</div>
                <div class="content">
                    Привет! Я <b>AWESOME AI 2026</b> на базе GigaChat.<br>
                    Задай любой вопрос — я отвечу за 2-3 секунды! 🚀
                    <span class="time">now</span>
                </div>
            </div>
            <div class="typing-indicator" id="typingIndicator"><span></span><span></span><span></span></div>
        </div>

        <div id="input-area">
            <textarea id="userInput" rows="1" placeholder="Спроси у AWESOME AI..." onkeydown="handleKey(event)"></textarea>
            <button class="send-btn" id="sendBtn" onclick="sendMessage()">➤</button>
        </div>
    </main>
</div>

<script>
    // ============================================================
    // CONFIG
    // ============================================================
    const USER_ID = localStorage.getItem('awesome_user_id') || (() => {
        const id = 'user_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6);
        localStorage.setItem('awesome_user_id', id);
        return id;
    })();

    let USER_NAME = localStorage.getItem('awesome_username') || 'Гость';
    let PREMIUM = false;
    let REMAINING = 20;

    // ============================================================
    // STATE
    // ============================================================
    let chatHistory = [];
    let currentChatId = null;
    let isSending = false;

    // ============================================================
    // DOM REFS
    // ============================================================
    const messagesEl = document.getElementById('messages');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const historyList = document.getElementById('historyList');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    // ============================================================
    // USER DATA
    // ============================================================
    function loadUserData() {
        fetch(`/api/user?user_id=${USER_ID}`)
            .then(res => res.json())
            .then(data => {
                if (data.user_id) {
                    USER_NAME = data.username || 'Гость';
                    PREMIUM = data.premium || false;
                    REMAINING = data.remaining || 0;
                    localStorage.setItem('awesome_username', USER_NAME);
                    updateUI();
                }
            })
            .catch(() => {
                // fallback
                updateUI();
            });
    }

    function updateUI() {
        document.getElementById('userName').textContent = USER_NAME;
        document.getElementById('userAvatar').textContent = USER_NAME[0].toUpperCase() || '👤';
        document.getElementById('userStatus').textContent = PREMIUM ? '💎 Premium' : '🔓 Бесплатный';
        document.getElementById('userLimit').textContent = PREMIUM ? '♾️' : `${REMAINING}/день`;
    }

    // ============================================================
    // HISTORY (localStorage + Supabase)
    // ============================================================
    function loadHistory() {
        const saved = localStorage.getItem('awesome_history');
        if (saved) {
            try {
                chatHistory = JSON.parse(saved);
                renderHistory();
                if (chatHistory.length > 0) {
                    const last = chatHistory[chatHistory.length - 1];
                    currentChatId = last.id;
                    renderMessages(last.messages);
                }
                return;
            } catch(e) {}
        }
        // Если нет локальной истории — создаём новый чат
        if (chatHistory.length === 0) {
            newChat();
        }
    }

    function saveHistory() {
        localStorage.setItem('awesome_history', JSON.stringify(chatHistory));
        // Сохраняем в Supabase через API (опционально)
        const chat = chatHistory.find(c => c.id === currentChatId);
        if (chat) {
            fetch('/api/chat/history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: USER_ID,
                    chat_id: chat.id,
                    title: chat.title,
                    messages: chat.messages
                })
            }).catch(() => {});
        }
    }

    function renderHistory() {
        historyList.innerHTML = '';
        if (chatHistory.length === 0) {
            historyList.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:13px;text-align:center;">Нет чатов</div>';
            return;
        }
        chatHistory.slice().reverse().forEach(chat => {
            const div = document.createElement('div');
            div.className = 'history-item' + (chat.id === currentChatId ? ' active' : '');
            div.innerHTML = `<span class="icon">💬</span> ${chat.title || 'Чат'}`;
            div.onclick = () => switchChat(chat.id);
            historyList.appendChild(div);
        });
    }

    function switchChat(chatId) {
        currentChatId = chatId;
        const chat = chatHistory.find(c => c.id === chatId);
        if (chat) {
            renderMessages(chat.messages);
            renderHistory();
        }
        closeSidebar();
    }

    function newChat() {
        const id = 'chat_' + Date.now();
        const newChat = {
            id: id,
            title: 'Новый чат',
            messages: [
                { role: 'bot', content: 'Привет! Чем могу помочь? 🧠', time: new Date().toISOString() }
            ]
        };
        chatHistory.push(newChat);
        currentChatId = id;
        renderMessages(newChat.messages);
        renderHistory();
        saveHistory();
        closeSidebar();
        userInput.focus();
    }

    function clearChat() {
        if (!currentChatId) return;
        const chat = chatHistory.find(c => c.id === currentChatId);
        if (chat) {
            chat.messages = [
                { role: 'bot', content: 'Чат очищен. Задай новый вопрос! 🧠', time: new Date().toISOString() }
            ];
            renderMessages(chat.messages);
            saveHistory();
        }
    }

    // ============================================================
    // RENDER MESSAGES
    // ============================================================
    function renderMessages(messages) {
        messagesEl.innerHTML = '';
        messages.forEach(msg => {
            addMessageToDOM(msg.role, msg.content, msg.time, false);
        });
        scrollToBottom();
    }

    function addMessageToDOM(role, content, time, animate = true) {
        const div = document.createElement('div');
        div.className = `msg ${role}`;
        if (animate) div.style.animation = 'none';
        const avatar = role === 'user' ? (USER_NAME[0] || '👤') : '🧠';
        const timeStr = time ? new Date(time).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' }) : 'now';
        div.innerHTML = `
            <div class="avatar">${avatar}</div>
            <div class="content">
                ${formatContent(content)}
                <span class="time">${timeStr}</span>
            </div>
        `;
        messagesEl.insertBefore(div, typingIndicator);
        if (animate) {
            requestAnimationFrame(() => { div.style.animation = ''; });
        }
        scrollToBottom();
    }

    function formatContent(text) {
        text = text.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
        text = text.replace(/\*(.+?)\*/g, '<i>$1</i>');
        text = text.replace(/`(.+?)`/g, '<code>$1</code>');
        text = text.replace(/\n/g, '<br>');
        text = text.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');
        return text;
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        });
    }

    // ============================================================
    // SEND MESSAGE
    // ============================================================
    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text || isSending) return;

        isSending = true;
        sendBtn.disabled = true;
        userInput.disabled = true;

        const userMsg = { role: 'user', content: text, time: new Date().toISOString() };
        addMessageToDOM('user', text, userMsg.time);
        userInput.value = '';
        userInput.style.height = 'auto';

        typingIndicator.style.display = 'flex';

        // Сохраняем в историю
        let chat = chatHistory.find(c => c.id === currentChatId);
        if (!chat) { newChat(); chat = chatHistory.find(c => c.id === currentChatId); }
        if (chat) {
            chat.messages.push(userMsg);
            if (chat.messages.length === 2 && chat.messages[0].role === 'bot') {
                chat.title = text.slice(0, 30) + (text.length > 30 ? '...' : '');
            }
            saveHistory();
            renderHistory();
        }

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID, text, chat_id: currentChatId })
            });

            typingIndicator.style.display = 'none';

            if (response.ok) {
                const data = await response.json();
                const botMsg = {
                    role: 'bot',
                    content: data.response || '❌ Не удалось получить ответ',
                    time: new Date().toISOString()
                };
                addMessageToDOM('bot', botMsg.content, botMsg.time);
                if (chat) {
                    chat.messages.push(botMsg);
                    saveHistory();
                    renderHistory();
                }
                // Обновляем лимиты
                loadUserData();
            } else {
                const err = await response.json();
                addMessageToDOM('bot', `⚠️ ${err.error || 'Ошибка сервера'}`, new Date().toISOString());
            }
        } catch (e) {
            typingIndicator.style.display = 'none';
            addMessageToDOM('bot', `⚠️ Ошибка соединения: ${e.message}`, new Date().toISOString());
        }

        isSending = false;
        sendBtn.disabled = false;
        userInput.disabled = false;
        userInput.focus();
        scrollToBottom();
    }

    // ============================================================
    // UI HELPERS
    // ============================================================
    function handleKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
    }

    function toggleSidebar() {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('active');
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
    }

    // ============================================================
    // INIT
    // ============================================================
    loadUserData();
    loadHistory();

    userInput.focus();
    overlay.addEventListener('click', closeSidebar);

    console.log('🧠 AWESOME AI 2026 веб-версия');
    console.log('👤', USER_NAME, 'ID:', USER_ID);
</script>
</body>
</html>
