
import os
import json
import base64
from datetime import datetime, timezone, timedelta

# ================= 配置区 =================
BASE_DIR = "docs"
REPO_NAME = "Instagram-File"
tz_utc_8 = timezone(timedelta(hours=8))

# ================= 批注核心引擎 (注入单集精读) =================
ENGINE_SCRIPT = r"""
function renderMarkdown(text) {
    if (typeof marked === 'undefined') return text;
    let safeText = text.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                       .replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '')
                       .replace(/\bon[a-z]+\s*=/gi, 'data-blocked=');
    return marked.parse(safeText);
}

let syncTimeout = null;
function scheduleSync() {
    const statusMsg = document.getElementById('sync-status');
    statusMsg.style.display = 'inline-block';
    statusMsg.style.backgroundColor = '#f39c12';
    statusMsg.innerText = '⏳ 更改已记录，5秒后自动同步...';
    if (syncTimeout) clearTimeout(syncTimeout);
    syncTimeout = setTimeout(syncToGitHub, 5000);
}

const AI_PROMPT = `你是一位精通英语社交网络用语、Instagram/Threads 流行梗和 Gen-Z 俚语的英语名师。
请分析以下 Instagram 英文评论，严格按照以下 Markdown 格式输出（不要输出任何废话）：

### 📌 地道中文翻译
[此处填写结合语境的地道口语化翻译]

### 📌 俚语与核心表达 (Slang & Expressions)
- **[单词/俚语/缩写]**   = [中文释义]   （[详细解析：包括缩写还原(如 ngl=not gonna lie, fr=for real)、梗背景或地道使用场景]）

评论内容：
`;

async function fetchCustom(text, url, apiKey, modelName) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: modelName,
            messages: [
                { role: 'system', content: 'You are an expert English teacher specialized in social media slang.' },
                { role: 'user', content: AI_PROMPT + `"${text}"` }
            ],
            temperature: 0.3
        })
    });
    if (!res.ok) throw new Error(`自定义API Error: ${res.status}`);
    const json = await res.json();
    if (json.choices && json.choices.length > 0) return json.choices[0].message.content.trim();
    throw new Error('自定义API返回数据异常');
}

async function fetchGroq(text, apiKey, modelName) {
    const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: modelName,
            messages: [
                { role: 'system', content: 'You are an expert English teacher specialized in social media slang.' },
                { role: 'user', content: AI_PROMPT + `"${text}"` }
            ],
            temperature: 0.3
        })
    });
    if (!res.ok) throw new Error(`Groq API Error: ${res.status}`);
    const json = await res.json();
    if (json.choices && json.choices.length > 0) return json.choices[0].message.content.trim();
    throw new Error('Groq返回数据异常');
}

async function fetchGLM(text, apiKey, modelName) {
    const res = await fetch('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: modelName,
            messages: [
                { role: 'system', content: 'You are an expert English teacher specialized in social media slang.' },
                { role: 'user', content: AI_PROMPT + `"${text}"` }
            ],
            temperature: 0.3
        })
    });
    if (!res.ok) throw new Error(`智谱GLM API Error: ${res.status}`);
    const json = await res.json();
    if (json.choices && json.choices.length > 0) return json.choices[0].message.content.trim();
    throw new Error('智谱GLM返回数据异常');
}

async function executeAIPipeline(text) {
    const pref = localStorage.getItem('PREFERRED_AI') || 'groq';
    
    const groqKey = (localStorage.getItem('GROQ_API_KEY') || '').replace(/[^\x20-\x7E]/g, '');
    const glmKey = (localStorage.getItem('GLM_API_KEY') || '').replace(/[^\x20-\x7E]/g, '');
    const customKey = (localStorage.getItem('CUSTOM_API_KEY') || '').replace(/[^\x20-\x7E]/g, '');
    
    const groqModel = (localStorage.getItem('GROQ_MODEL') || 'llama-3.3-70b-versatile').trim();
    const glmModel = (localStorage.getItem('GLM_MODEL') || 'GLM-4.5-Flash').trim();
    const customUrl = (localStorage.getItem('CUSTOM_API_URL') || '').trim();
    const customModel = (localStorage.getItem('CUSTOM_MODEL') || '').trim();

    if ((!groqKey && !glmKey && !customKey) || (!groqModel && !glmModel && !customModel)) throw new Error('MISSING_KEYS_OR_MODELS');

    const runGroq = async () => { if (!groqKey || !groqModel) throw new Error("Groq 配置缺失"); return await fetchGroq(text, groqKey, groqModel); };
    const runGLM = async () => { if (!glmKey || !glmModel) throw new Error("智谱GLM 配置缺失"); return await fetchGLM(text, glmKey, glmModel); };
    const runCustom = async () => { if (!customUrl || !customKey || !customModel) throw new Error("自定义配置缺失"); return await fetchCustom(text, customUrl, customKey, customModel); };

    if (pref === 'custom') {
        try { return await runCustom(); } catch (err) {
            if (groqKey && groqModel) return await runGroq();
            if (glmKey && glmModel) return await runGLM();
            throw err;
        }
    } else if (pref === 'groq') {
        try { return await runGroq(); } catch (err) {
            if (glmKey && glmModel) return await runGLM();
            throw err;
        }
    } else {
        try { return await runGLM(); } catch (err) {
            if (groqKey && groqModel) return await runGroq();
            throw err;
        }
    }
}

function initAnnotations() {
    document.querySelectorAll('.para-wrap').forEach(wrap => {
        const view = wrap.querySelector('.anno-view');
        const edit = wrap.querySelector('.anno-edit');
        const toggle = wrap.querySelector('.anno-toggle');
        const aiToggle = wrap.querySelector('.ai-toggle');
        const box = wrap.querySelector('.anno-box');

        const rawText = edit.value.trim();
        if (rawText) { toggle.classList.add('has-anno'); view.innerHTML = renderMarkdown(rawText); }
        
        if (aiToggle) {
            aiToggle.addEventListener('click', async (e) => {
                e.preventDefault(); e.stopPropagation();
                if (aiToggle.classList.contains('loading')) return;
                
                if (edit.value.trim().length > 0) {
                    const confirmOverwrite = confirm('⚠️ 当前已有批注内容，是否重新生成并覆盖？');
                    if (!confirmOverwrite) return;
                }
                
                const groqKey = (localStorage.getItem('GROQ_API_KEY') || '').trim();
                const glmKey = (localStorage.getItem('GLM_API_KEY') || '').trim();
                const customKey = (localStorage.getItem('CUSTOM_API_KEY') || '').trim();

                if (!groqKey && !glmKey && !customKey) { alert('⚠️ 请先返回日历配置中心设置 AI API Key！'); return; }

                const pClone = wrap.querySelector('.card-text').cloneNode(true);
                pClone.querySelectorAll('.anno-toggle, .ai-toggle').forEach(el => el.remove());
                const pText = pClone.textContent.trim();
                if (!pText) return;

                aiToggle.classList.add('loading');
                const statusMsg = document.getElementById('sync-status');
                statusMsg.style.display = 'inline-block';
                statusMsg.style.backgroundColor = '#e1306c';
                statusMsg.innerText = '🤖 AI 拆解俚语中...';

                try {
                    const aiContent = await executeAIPipeline(pText);
                    box.style.display = 'block'; view.style.display = 'none'; edit.style.display = 'block';
                    edit.value = aiContent; edit.focus(); edit.blur();
                    statusMsg.style.backgroundColor = '#2ea44f'; statusMsg.innerText = '✅ 解析成功';
                    setTimeout(() => { if (statusMsg.innerText.includes('成功')) statusMsg.style.display = 'none'; }, 2000);
                } catch (err) {
                    alert(err.message === 'MISSING_KEYS_OR_MODELS' ? '⚠️ 请返回配置AI密钥和模型！' : '❌ AI 解析失败: ' + err.message);
                    statusMsg.style.display = 'none';
                } finally { aiToggle.classList.remove('loading'); }
            });
        }

        toggle.addEventListener('click', (e) => {
            e.preventDefault(); e.stopPropagation();
            if (box.style.display === 'block') { box.style.display = 'none'; }
            else {
                box.style.display = 'block';
                if (!edit.value.trim()) { view.style.display = 'none'; edit.style.display = 'block'; setTimeout(() => edit.focus(), 50); }
                else { view.style.display = 'block'; edit.style.display = 'none'; }
            }
        });

        const triggerEdit = () => { view.style.display = 'none'; edit.style.display = 'block'; setTimeout(() => edit.focus(), 50); };
        view.addEventListener('dblclick', () => { box.style.display = 'none'; });
        
        let lastTap = 0;
        view.addEventListener('touchstart', e => {
            if (e.touches.length === 2) { triggerEdit(); }
            else if (e.touches.length === 1) {
                const currentTime = new Date().getTime();
                if (currentTime - lastTap < 500 && currentTime - lastTap > 0) { box.style.display = 'none'; }
                lastTap = currentTime;
            }
        }, {passive: true});

        edit.addEventListener('blur', () => {
            const newVal = edit.value.trim();
            try { view.innerHTML = newVal ? renderMarkdown(newVal) : ''; } catch(e){}
            edit.style.display = 'none';
            if (newVal) { view.style.display = 'block'; toggle.classList.add('has-anno'); }
            else { view.style.display = 'none'; box.style.display = 'none'; toggle.classList.remove('has-anno'); }
            
            if (edit.getAttribute('data-old-val') !== newVal) {
                edit.setAttribute('data-old-val', newVal);
                scheduleSync();
            }
        });

        edit.setAttribute('data-old-val', rawText);
    });
}
window.onload = initAnnotations;

function escapeHTML(str) {
    if (typeof str !== 'string') return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function reconstructSelfHTML() {
    const dataTag = document.getElementById('page-data');
    if (!dataTag) throw new Error("Missing state data!");
    const pageData = JSON.parse(dataTag.textContent);
    
    document.querySelectorAll('.chat-message').forEach((msg, idx) => {
        const edit = msg.querySelector('.anno-edit');
        if (pageData.comments[idx] && edit) {
            pageData.comments[idx].annotation = edit.value || "";
        }
    });

    const newJsonStr = JSON.stringify(pageData).replace(/</g, '\\u003c');
    const engineText = document.getElementById('matrix-engine').textContent;
    const styleText = document.querySelector('style').textContent;
    const titleText = document.title;

    let comments_html = "";
    pageData.comments.forEach(c => {
        comments_html += `
        <div class="chat-message">
            <img src="${escapeHTML(c.avatar)}" class="avatar" alt="avatar" loading="lazy">
            <div class="message-content">
                <div class="message-header">
                    <span class="author">${escapeHTML(c.author)}</span>
                    <span class="likes">❤️ ${escapeHTML(c.likes_str)}</span>
                </div>
                <div class="para-wrap">
                    <div class="bubble card-text">${escapeHTML(c.text)}<span class="anno-toggle" title="点击添加/查看批注">🔴</span><span class="ai-toggle" title="AI俚语解析">🤖</span></div>
                    <div class="anno-box" style="display:none;">
                        <div class="anno-view markdown-body"></div>
                        <textarea class="anno-edit" style="display:none;" placeholder="在此记录该评论的俚语拆解或灵感...">${escapeHTML(c.annotation)}</textarea>
                    </div>
                </div>
            </div>
        </div>`;
    });

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>${escapeHTML(titleText)}</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"><\/script>
    <style>${styleText}</style>
</head>
<body>
    <div class="nav-back">
        <a href="../../index.html">🔙 返回日曆樞紐</a>
        <span id="sync-status" class="sync-status"></span>
    </div>
    <div class="container">
        <h2 style="text-align: center; margin-bottom: 25px; color: #333;">📅 ${pageData.year}-${String(pageData.month).padStart(2,'0')}-${String(pageData.day).padStart(2,'0')}</h2>
        
        <div class="post-card">
            <a href="${escapeHTML(pageData.post.url)}" target="_blank"><img src="${escapeHTML(pageData.post.thumb)}" class="post-thumb" alt="Thumbnail"></a>
            <div class="post-info">
                <span class="p-channel">${escapeHTML(pageData.post.channel)}</span>
                <h1 class="p-title">${escapeHTML(pageData.post.title)}</h1>
                <div class="p-actions">
                    <span class="timestamp">更新於: ${escapeHTML(pageData.post.now_str)}</span>
                    <a href="${escapeHTML(pageData.post.url)}" target="_blank" class="btn-play">▶ 原帖</a>
                </div>
            </div>
        </div>

        <div class="chat-container">
            ${comments_html ? comments_html : '<div class="empty-state">暫无评论。</div>'}
        </div>
    </div>
    <script id="page-data" type="application/json">${newJsonStr}<\/script>
    <script id="matrix-engine">${engineText}<\/script>
</body>
</html>`;
}

async function syncToGitHub() {
    const token = (localStorage.getItem('GH_TOKEN') || '').replace(/[^\x20-\x7E]/g, '');
    const owner = (localStorage.getItem('GH_OWNER') || '').replace(/[^\x20-\x7E]/g, '');
    const repo = 'Instagram-File';
    
    if(!token || !owner) { alert('缺少 GitHub Token，无法同步！'); return; }

    const statusMsg = document.getElementById('sync-status');
    statusMsg.style.display = 'inline-block';
    statusMsg.style.backgroundColor = '#2ea44f';
    statusMsg.innerText = '📡 同步中...';

    const pureHtml = reconstructSelfHTML();
    let urlPath = window.location.pathname;
    const match = urlPath.match(/(\d{4}\/\d{1,2}\/[^/]+\.html)$/);
    let fileRelPath = match ? "docs/" + match[1] : (urlPath.includes('docs/') ? urlPath.substring(urlPath.indexOf('docs/')) : null);
    
    if (!fileRelPath) { alert('路径解析失败！'); statusMsg.style.display = 'none'; return; }

    try {
        const base64Html = btoa(encodeURIComponent(pureHtml).replace(/%([0-9A-F]{2})/g, function(match, p1) { return String.fromCharCode('0x' + p1); }));
        
        const getRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${fileRelPath}?t=${Date.now()}`, { headers: { 'Authorization': `token ${token}` }, cache: 'no-store' });
        if (!getRes.ok) throw new Error('API 获取 SHA 失败');
        const fileData = await getRes.json();

        const putRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${fileRelPath}`, {
            method: 'PUT',
            headers: { 'Authorization': `token ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: `Auto-save annotation`, content: base64Html, sha: fileData.sha })
        });

        if(putRes.ok) {
            statusMsg.style.backgroundColor = '#2ea44f'; statusMsg.innerText = '✅ 云端已同步';
            setTimeout(() => { if (statusMsg.innerText === '✅ 云端已同步') statusMsg.style.display = 'none'; }, 3000);
        } else throw new Error('Put 请求失败');
    } catch(e) {
        statusMsg.style.backgroundColor = '#e74c3c'; statusMsg.innerText = '❌ 同步失败(点击重试)';
        statusMsg.style.cursor = 'pointer';
        statusMsg.onclick = () => { statusMsg.onclick = null; statusMsg.style.cursor = 'default'; syncToGitHub(); };
    }
}
"""

def generate_index_template():
    archive_data = {}
    if os.path.exists(BASE_DIR):
        years = [d for d in os.listdir(BASE_DIR) if d.isdigit()]
        for year in years:
            months = [d for d in os.listdir(os.path.join(BASE_DIR, year)) if d.isdigit()]
            for month in months:
                files = sorted([f for f in os.listdir(os.path.join(BASE_DIR, year, month)) if f.endswith('.html')], reverse=True)
                for file in files:
                    try:
                        parts = file.replace(".html", "").split('_')
                        if len(parts) >= 4:
                            f_year, f_month, f_day = str(int(parts[0])), str(int(parts[1])), str(int(parts[2]))
                            time_str = f"{parts[3][:2]}:{parts[3][2:4]}"
                            file_path = f"{year}/{month}/{file}"
                            title = "📸 Instagram 贴文"
                            
                            if f_year not in archive_data: archive_data[f_year] = {}
                            if f_month not in archive_data[f_year]: archive_data[f_year][f_month] = {}
                            if f_day not in archive_data[f_year][f_month]: archive_data[f_year][f_month][f_day] = []
                            
                            archive_data[f_year][f_month][f_day].append({
                                "time": time_str,
                                "path": file_path,
                                "title": title
                            })
                    except Exception:
                        pass

    json_data = json.dumps(archive_data)
    engine_b64 = base64.b64encode(ENGINE_SCRIPT.encode('utf-8')).decode('utf-8')

    html_template = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Instagram 潮语精读日历</title>
    <style>
        :root {
            --bg: #fafafa; --text: #262626; --muted: #8e8e8e;
            --primary: #d62976; --ins-gradient: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%);
            --border: #dbdbdb; --card: #fff;
        }
        body, html { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; background: var(--bg); margin: 0; padding: 0; color: var(--text); }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 20px; }
        
        .manual-fetch-bar { background: var(--card); padding: 12px 15px; display: flex; gap: 10px; align-items: center; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 20; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }
        .fetch-input { flex: 1; padding: 10px 15px; border: 1px solid #ccc; border-radius: 20px; font-size: 14px; outline: none; background: #fafafa; transition: border 0.2s; }
        .fetch-input:focus { border-color: var(--primary); background: #fff; }
        .settings-btn { background: none; border: none; font-size: 20px; cursor: pointer; padding: 5px; }
        
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: var(--card); border-radius: 16px; padding: 20px; width: 100%; max-width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-height: 85vh; overflow-y: auto; }
        .modal-title { margin: 0 0 15px 0; font-size: 18px; font-weight: bold; color: #1c1e21; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 5px; font-weight: bold; }
        .form-group input, .form-group select { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; background: #fff; color: #333; }
        
        .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
        .btn { padding: 10px 18px; border-radius: 8px; border: none; font-size: 14px; font-weight: bold; cursor: pointer; }
        .btn-cancel { background: #eee; color: #333; }
        .btn-save { background: var(--ins-gradient); color: #fff; }
        
        .controls { background: var(--bg); padding: 15px 20px; display: flex; justify-content: center; align-items: center; gap: 8px; border-bottom: 1px solid var(--border); }
        .control-btn { background: var(--ins-gradient); color: #fff; border: none; border-radius: 6px; padding: 8px 12px; font-size: 14px; cursor: pointer; font-weight: bold; }
        .select-box { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 15px; background: #fff; outline: none; font-weight: bold; cursor: pointer; color: #333; }
        
        .calendar-wrapper { background: var(--card); padding: 15px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
        .weekdays { display: grid; grid-template-columns: repeat(7, 1fr); text-align: center; font-weight: bold; font-size: 13px; color: var(--muted); margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; }
        .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px; }
        .day-cell { aspect-ratio: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer; position: relative; }
        .day-cell.empty { visibility: hidden; }
        .day-cell.has-news { color: var(--text); }
        .day-cell.no-news { color: #ccc; }
        .day-cell.selected { background: #fdf0f4; border: 1px solid var(--primary); color: var(--primary); font-weight: bold; }
        .day-cell.today { background: #f0f0f0; color: #333; }
        .dot { width: 5px; height: 5px; background: var(--ins-gradient); border-radius: 50%; position: absolute; bottom: 6px; display: none; }
        .day-cell.has-news .dot { display: block; }
        
        .news-section { padding: 0 15px; }
        .news-item-wrapper { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; width: 100%; box-sizing: border-box; }
        .news-item { flex: 1; min-width: 0; background: var(--card); border-radius: 14px; padding: 16px; display: flex; align-items: center; text-decoration: none; color: var(--text); box-shadow: 0 2px 8px rgba(0,0,0,0.03); border-left: 4px solid var(--primary); overflow: hidden; }
        .news-title { font-size: 15px; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: bold; display: block; width: 100%; }
        .delete-btn { background: #ff3b30; color: white; border: none; border-radius: 10px; padding: 0 15px; height: 54px; font-size: 16px; cursor: pointer; display: none; }
        
        .empty-state { text-align: center; padding: 40px 20px; color: var(--muted); font-size: 14px; background: var(--card); border-radius: 14px; }
        
        #loadingBar { height: 3px; background: var(--ins-gradient); width: 0%; transition: width 0.3s; position: absolute; top: 0; left: 0; z-index: 30; }
        .toast-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.45); z-index: 99999; justify-content: center; align-items: center; }
        .toast-card { background: #ffffff; border-radius: 18px; padding: 25px 30px; text-align: center; box-shadow: 0 12px 30px rgba(0,0,0,0.2); max-width: 280px; width: 75%; }
        .toast-icon { font-size: 40px; margin-bottom: 8px; }
        .toast-text { font-size: 16px; font-weight: bold; color: #222; margin: 0; }
    </style>
</head>
<body>
    <div id="loadingBar"></div>
    <div class="toast-overlay" id="toastOverlay">
        <div class="toast-card">
            <div class="toast-icon">✅</div>
            <p class="toast-text" id="toastText">配置已保存！</p>
        </div>
    </div>

    <div class="manual-fetch-bar">
        <input type="text" id="insUrlInput" class="fetch-input" placeholder="粘贴 Instagram Post / Reel 链接，回车抓取..." autocomplete="off">
        <button class="settings-btn" onclick="openConfigModal()">⚙️</button>
    </div>

    <div class="modal-overlay" id="settingsModal">
        <div class="modal-content">
            <h3 class="modal-title">Instagram 配置中心</h3>
            <p style="font-size:12px; color:#888; margin-top:-10px; margin-bottom:15px;">专属配置已隔离，不会与 Twitter/TikTok 产生覆盖。</p>
            
            <div class="form-group"><label>Instagram RapidAPI Key</label><input type="password" id="cfgRapidKey" placeholder="在此粘贴你的 RapidAPI Key"></div>
            <div class="form-group"><label>Instagram RapidAPI Host</label><input type="text" id="cfgRapidHost" placeholder="instagram360.p.rapidapi.com"></div>
            
            <div style="border-top:1px dashed #ddd; margin: 15px 0;"></div>
            <div class="form-group"><label>GitHub Personal Access Token</label><input type="password" id="cfgGhToken" placeholder="ghp_..."></div>
            <div class="form-group" style="display:flex; gap:10px;">
                <div style="flex:1;"><label>GitHub 用户名</label><input type="text" id="cfgGhOwner" placeholder="例如 moodHappy"></div>
                <div style="flex:1;"><label>仓库 (写死)</label><input type="text" value="Instagram-File" readonly disabled style="background:#eee; color:#888;"></div>
            </div>

            <div style="border-top:1px dashed #ddd; margin: 15px 0;"></div>
            <div class="form-group">
                <label>首选 AI 引擎</label>
                <select id="cfgPrefAI">
                    <option value="groq">Groq</option>
                    <option value="glm">智谱</option>
                    <option value="custom">自定义 (兼容OpenAI协议)</option>
                </select>
            </div>
            
            <div class="form-group"><label>自定义 API URL</label><input type="text" id="cfgCustomURL" placeholder="https://api.deepseek.com/v1/chat/completions"></div>
            <div class="form-group" style="display:flex; gap:10px;">
                <div style="flex:1;"><label>自定义 Key</label><input type="password" id="cfgCustomKey" placeholder="sk-..."></div>
                <div style="flex:1;"><label>自定义 模型</label><input type="text" id="cfgCustomModel" placeholder="deepseek-chat"></div>
            </div>

            <div style="border-top:1px dashed #ddd; margin: 15px 0;"></div>
            <div class="form-group" style="display:flex; gap:10px;">
                <div style="flex:1;"><label>Groq Key</label><input type="password" id="cfgGroq"></div>
                <div style="flex:1;"><label>Groq 模型</label><input type="text" id="cfgGroqModel" value="llama-3.3-70b-versatile"></div>
            </div>
            <div class="form-group" style="display:flex; gap:10px;">
                <div style="flex:1;"><label>智谱 Key</label><input type="password" id="cfgGLM"></div>
                <div style="flex:1;"><label>智谱 模型</label><input type="text" id="cfgGLMModel" value="GLM-4.5-Flash"></div>
            </div>
            
            <div class="modal-actions">
                <button type="button" class="btn btn-cancel" onclick="closeConfigModal()">取消</button>
                <button type="button" class="btn btn-save" onclick="saveConfigAndNotify(event)">保存配置</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="controls">
            <button class="control-btn" id="prevBtn">&lt;</button>
            <select class="select-box" id="yearSelect"></select>
            <select class="select-box" id="monthSelect">
                <option value="1">01月</option><option value="2">02月</option><option value="3">03月</option>
                <option value="4">04月</option><option value="5">05月</option><option value="6">06月</option>
                <option value="7">07月</option><option value="8">08月</option><option value="9">09月</option>
                <option value="10">10月</option><option value="11">11月</option><option value="12">12月</option>
            </select>
            <button class="control-btn" id="nextBtn">&gt;</button>
            <button class="control-btn" id="todayBtn">今天</button>
        </div>

        <div class="calendar-wrapper">
            <div class="weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
            <div class="days-grid" id="daysGrid"></div>
        </div>

        <div class="news-section"><div id="newsList"></div></div>
    </div>

    <script>
        const archiveData = /*DATA_START*/REPLACEME_JSON_DATA/*DATA_END*/;
        const today = new Date();
        const AppState = { year: today.getFullYear(), month: today.getMonth() + 1, day: today.getDate(), deleteMode: false };

        function popToast(msg, duration = 1200) {
            const overlay = document.getElementById('toastOverlay');
            document.getElementById('toastText').innerText = msg;
            overlay.style.display = 'flex';
            setTimeout(() => { overlay.style.display = 'none'; }, duration);
        }

        function openConfigModal() {
            document.getElementById('cfgRapidKey').value = localStorage.getItem('INS_RAPIDAPI_KEY') || '';
            document.getElementById('cfgRapidHost').value = localStorage.getItem('INS_RAPIDAPI_HOST') || 'instagram360.p.rapidapi.com';
            document.getElementById('cfgGhToken').value = localStorage.getItem('GH_TOKEN') || '';
            document.getElementById('cfgGhOwner').value = localStorage.getItem('GH_OWNER') || '';
            
            document.getElementById('cfgPrefAI').value = localStorage.getItem('PREFERRED_AI') || 'groq';
            document.getElementById('cfgCustomURL').value = localStorage.getItem('CUSTOM_API_URL') || '';
            document.getElementById('cfgCustomKey').value = localStorage.getItem('CUSTOM_API_KEY') || '';
            document.getElementById('cfgCustomModel').value = localStorage.getItem('CUSTOM_MODEL') || '';
            document.getElementById('cfgGroq').value = localStorage.getItem('GROQ_API_KEY') || '';
            document.getElementById('cfgGroqModel').value = localStorage.getItem('GROQ_MODEL') || 'llama-3.3-70b-versatile';
            document.getElementById('cfgGLM').value = localStorage.getItem('GLM_API_KEY') || '';
            document.getElementById('cfgGLMModel').value = localStorage.getItem('GLM_MODEL') || 'GLM-4.5-Flash';
            document.getElementById('settingsModal').style.display = 'flex';
        }
        function closeConfigModal() { document.getElementById('settingsModal').style.display = 'none'; }

        function saveConfigAndNotify(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            // 写入本地存储前也做一次清理，防手滑
            localStorage.setItem('INS_RAPIDAPI_KEY', (document.getElementById('cfgRapidKey').value || '').trim().replace(/[^\x20-\x7E]/g, ''));
            localStorage.setItem('INS_RAPIDAPI_HOST', (document.getElementById('cfgRapidHost').value || '').trim().replace(/[^\x20-\x7E]/g, '') || 'instagram360.p.rapidapi.com');
            localStorage.setItem('GH_TOKEN', (document.getElementById('cfgGhToken').value || '').trim().replace(/[^\x20-\x7E]/g, ''));
            localStorage.setItem('GH_OWNER', (document.getElementById('cfgGhOwner').value || '').trim().replace(/[^\x20-\x7E]/g, ''));
            
            localStorage.setItem('PREFERRED_AI', document.getElementById('cfgPrefAI').value || 'groq');
            localStorage.setItem('CUSTOM_API_URL', (document.getElementById('cfgCustomURL').value || '').trim());
            localStorage.setItem('CUSTOM_API_KEY', (document.getElementById('cfgCustomKey').value || '').trim().replace(/[^\x20-\x7E]/g, ''));
            localStorage.setItem('CUSTOM_MODEL', (document.getElementById('cfgCustomModel').value || '').trim());
            localStorage.setItem('GROQ_API_KEY', (document.getElementById('cfgGroq').value || '').trim().replace(/[^\x20-\x7E]/g, ''));
            localStorage.setItem('GROQ_MODEL', (document.getElementById('cfgGroqModel').value || '').trim());
            localStorage.setItem('GLM_API_KEY', (document.getElementById('cfgGLM').value || '').trim().replace(/[^\x20-\x7E]/g, ''));
            localStorage.setItem('GLM_MODEL', (document.getElementById('cfgGLMModel').value || '').trim());

            closeConfigModal();
            popToast('配置已本地保存！', 1200);
        }

        function initSelects() {
            const yearSelect = document.getElementById('yearSelect');
            yearSelect.innerHTML = '';
            const allYears = new Set(Object.keys(archiveData).map(Number));
            for(let i = -5; i <= 50; i++) allYears.add(today.getFullYear() + i);
            Array.from(allYears).sort((a, b) => b - a).forEach(y => {
                const opt = document.createElement('option'); opt.value = y; opt.textContent = y + ' 年';
                yearSelect.appendChild(opt);
            });
        }

        function forceRender() {
            const maxDay = new Date(AppState.year, AppState.month, 0).getDate();
            if (AppState.day > maxDay) AppState.day = maxDay;

            document.getElementById('yearSelect').value = AppState.year;
            document.getElementById('monthSelect').value = AppState.month;
            
            const daysGrid = document.getElementById('daysGrid');
            const newsList = document.getElementById('newsList');
            daysGrid.innerHTML = ''; newsList.innerHTML = '';
            
            const firstDay = new Date(AppState.year, AppState.month - 1, 1).getDay() || 7;
            for (let i = 1; i < firstDay; i++) {
                const emptyCell = document.createElement('div'); emptyCell.className = 'day-cell empty';
                daysGrid.appendChild(emptyCell);
            }
            
            const monthData = (archiveData[AppState.year] && archiveData[AppState.year][AppState.month]) || {};
            for (let day = 1; day <= maxDay; day++) {
                const cell = document.createElement('div'); cell.className = 'day-cell'; cell.textContent = day;
                const dot = document.createElement('div'); dot.className = 'dot'; cell.appendChild(dot);
                
                if (monthData[day] && monthData[day].length > 0) cell.classList.add('has-news'); else cell.classList.add('no-news');
                if (AppState.year === today.getFullYear() && AppState.month === today.getMonth() + 1 && day === today.getDate()) cell.classList.add('today');
                if (day === AppState.day) cell.classList.add('selected');
                
                cell.onclick = () => { AppState.day = day; forceRender(); };
                daysGrid.appendChild(cell);
            }
            
            let dayData = (archiveData[AppState.year] && archiveData[AppState.year][AppState.month] && archiveData[AppState.year][AppState.month][AppState.day]) || null;
            if (dayData && dayData.length > 0) {
                dayData.forEach((news, index) => {
                    const wrapper = document.createElement('div'); wrapper.className = 'news-item-wrapper';
                    
                    const a = document.createElement('a'); a.href = news.path; a.className = 'news-item';
                    a.innerHTML = `<span class="news-title" style="color: var(--primary);">${news.title} (${news.time})</span>`;
                    wrapper.appendChild(a);
                    
                    const delBtn = document.createElement('button'); delBtn.className = 'delete-btn'; delBtn.innerHTML = '🗑️';
                    if (AppState.deleteMode) delBtn.style.display = 'block';
                    delBtn.onclick = async (e) => {
                        e.preventDefault();
                        if(confirm('确认删除此条目并同步删除云端文件吗？')) {
                            const pathToDelete = news.path;
                            dayData.splice(index, 1);
                            if (dayData.length === 0) delete archiveData[AppState.year][AppState.month][AppState.day];
                            forceRender();
                            await syncDeleteToGithub(pathToDelete);
                        }
                    };
                    wrapper.appendChild(delBtn); newsList.appendChild(wrapper);
                });
            } else {
                newsList.innerHTML = '<div class="empty-state">当日暂无 Instagram 归档记录 👀</div>';
            }
        }

        document.getElementById('yearSelect').addEventListener('change', (e) => { AppState.year = parseInt(e.target.value, 10); forceRender(); });
        document.getElementById('monthSelect').addEventListener('change', (e) => { AppState.month = parseInt(e.target.value, 10); forceRender(); });
        document.getElementById('prevBtn').addEventListener('click', () => { AppState.month--; if (AppState.month < 1) { AppState.month = 12; AppState.year--; } forceRender(); });
        document.getElementById('nextBtn').addEventListener('click', () => { AppState.month++; if (AppState.month > 12) { AppState.month = 1; AppState.year++; } forceRender(); });
        document.getElementById('todayBtn').addEventListener('click', () => { AppState.year = today.getFullYear(); AppState.month = today.getMonth() + 1; AppState.day = today.getDate(); forceRender(); });

        let lastTap = 0;
        document.querySelector('.calendar-wrapper').addEventListener('click', (e) => {
            const tapLength = new Date().getTime() - lastTap;
            if (tapLength < 500 && tapLength > 0) {
                AppState.deleteMode = !AppState.deleteMode;
                document.querySelectorAll('.delete-btn').forEach(btn => btn.style.display = AppState.deleteMode ? 'block' : 'none');
                e.preventDefault();
            }
            lastTap = new Date().getTime();
        });

        initSelects(); forceRender();

        async function syncDeleteToGithub(fileRelPath) {
            const ghToken = (localStorage.getItem('GH_TOKEN') || '').replace(/[^\x20-\x7E]/g, '');
            const ghOwner = (localStorage.getItem('GH_OWNER') || '').replace(/[^\x20-\x7E]/g, '');
            const ghRepo = 'Instagram-File';
            if (!ghToken || !ghOwner) return;

            try {
                const targetFilePath = `docs/${fileRelPath}`;
                const fileRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/${targetFilePath}`, { headers: { 'Authorization': `token ${ghToken}` } });
                if (fileRes.ok) {
                    const fileData = await fileRes.json();
                    await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/${targetFilePath}`, {
                        method: 'DELETE',
                        headers: { 'Authorization': `token ${ghToken}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Delete ins file: ${fileRelPath}`, sha: fileData.sha })
                    });
                }

                const idxRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, { headers: { 'Authorization': `token ${ghToken}` } });
                const idxData = await idxRes.json();
                const idxContent = decodeURIComponent(escape(atob(idxData.content)));
                
                const dataStart = idxContent.indexOf('/*DATA_START*/') + 14;
                const dataEnd = idxContent.indexOf('/*DATA_END*/');
                const newJsonStr = JSON.stringify(archiveData);
                const newIdxContent = idxContent.substring(0, dataStart) + newJsonStr + idxContent.substring(dataEnd);
                
                await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, {
                    method: 'PUT',
                    headers: { 'Authorization': `token ${ghToken}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: `Update index.html after deletion`, content: btoa(unescape(encodeURIComponent(newIdxContent))), sha: idxData.sha })
                });
            } catch(e) {}
        }

        function extractInstagramShortcode(url) {
            const match = url.match(/(?:p|reel|reels|share\/reel|share\/p)\/([A-Za-z0-9_-]+)/);
            if (match && match[1]) return match[1];
            if (/^[A-Za-z0-9_-]{8,15}$/.test(url.trim())) return url.trim();
            return null;
        }

        document.getElementById('insUrlInput').addEventListener('keypress', async function (e) {
            if (e.key === 'Enter') {
                const rawUrl = this.value.trim();
                if (!rawUrl) return;

                const rapidKey = (localStorage.getItem('INS_RAPIDAPI_KEY') || '').replace(/[^\x20-\x7E]/g, '');
                const rapidHost = (localStorage.getItem('INS_RAPIDAPI_HOST') || 'instagram360.p.rapidapi.com').replace(/[^\x20-\x7E]/g, '');
                const ghToken = (localStorage.getItem('GH_TOKEN') || '').replace(/[^\x20-\x7E]/g, '');
                const ghOwner = (localStorage.getItem('GH_OWNER') || '').replace(/[^\x20-\x7E]/g, '');
                const ghRepo = 'Instagram-File';
                
                if (!rapidKey || !ghToken || !ghOwner) {
                    alert('⚠️ 请先点击右上角 ⚙️ 配置 Instagram RapidAPI Key 和 GitHub Token！');
                    openConfigModal();
                    return;
                }

                const shortcode = extractInstagramShortcode(rawUrl);
                if (!shortcode) {
                    alert('⚠️ 未能识别此链接的 Shortcode，请确认是 Instagram Post 或 Reel 链接！');
                    return;
                }

                const loadingBar = document.getElementById('loadingBar');
                loadingBar.style.width = '20%';
                this.disabled = true;

                try {
                    let postTitle = `Instagram Post (${shortcode})`;
                    let postChannel = "@instagram_user";
                    let postThumb = "https://static.cdninstagram.com/rsrc.php/v3/yI/r/VsNE-OHk_8a.png";
                    let postUrl = `https://www.instagram.com/p/${shortcode}/`;

                    // ============================================
                    // 核心修改点1：获取 Detail，彻底移除 'Content-Type': 'application/json'
                    // ============================================
                    try {
                        const pRes = await fetch(`https://${rapidHost}/postdetail/?code_or_url=${shortcode}`, {
                            method: 'GET',
                            headers: { 
                                'x-rapidapi-host': rapidHost, 
                                'x-rapidapi-key': rapidKey
                            }
                        });
                        
                        if (pRes.ok) {
                            const pData = await pRes.json();
                            const item = pData.items ? pData.items[0] : (pData.data || pData);
                            const node = (item && item.node) ? item.node : item;

                            if (node) {
                                if (node.caption) {
                                    postTitle = typeof node.caption === 'string' ? node.caption : (node.caption.text || postTitle);
                                } else if (node.title) {
                                    postTitle = node.title;
                                }

                                const user = node.user || node.owner || {};
                                postChannel = '@' + (user.username || 'instagrammer');
                                
                                if (node.image_versions2 && node.image_versions2.candidates && node.image_versions2.candidates.length > 0) {
                                    postThumb = node.image_versions2.candidates[0].url;
                                } else if (node.display_uri || node.display_url) {
                                    postThumb = node.display_uri || node.display_url;
                                }
                            }
                        }
                    } catch(err) {
                        console.warn("详情接口受阻，降级使用默认标题抓取评论:", err);
                    }
                    
                    if (typeof postTitle === 'string') {
                        postTitle = postTitle.replace(/[\r\n]+/g, ' ').trim();
                        if (postTitle.length > 40) {
                            postTitle = postTitle.substring(0, 40) + '...';
                        }
                    }

                    loadingBar.style.width = '55%';

                    // ============================================
                    // 核心修改点2：获取 Comments，彻底移除 'Content-Type': 'application/json'
                    // ============================================
                    const cRes = await fetch(`https://${rapidHost}/postcomments/?code_or_url=${shortcode}`, {
                        method: 'GET',
                        headers: { 
                            'x-rapidapi-host': rapidHost, 
                            'x-rapidapi-key': rapidKey
                        }
                    });

                    if (!cRes.ok) throw new Error(`RapidAPI 获取评论失败 (状态码: ${cRes.status})`);
                    const cData = await cRes.json();
                    
                    let rawComments = [];
                    if (Array.isArray(cData)) rawComments = cData;
                    else if (cData.comments && Array.isArray(cData.comments)) rawComments = cData.comments;
                    else if (cData.data && Array.isArray(cData.data)) rawComments = cData.data;
                    else if (cData.data && cData.data.comments) rawComments = cData.data.comments;
                    else if (cData.data && cData.data.items) rawComments = cData.data.items;
                    else if (cData.items && Array.isArray(cData.items)) rawComments = cData.items;

                    let comments = [];
                    for (let c of rawComments) {
                        const cNode = c.node || c;
                        const text = cNode.text || '';
                        
                        if (text && /[\p{L}\p{N}]/u.test(text) && !text.includes('http')) {
                            const user = cNode.user || cNode.owner || {};
                            const authorName = user.username || "ins_user";
                            const avatar = user.profile_pic_url || (user.hd_profile_pic_url_info && user.hd_profile_pic_url_info.url) || "https://static.cdninstagram.com/rsrc.php/v3/yI/r/VsNE-OHk_8a.png";
                            const likes = parseInt(cNode.comment_like_count || cNode.like_count || 0);
                            
                            comments.push({
                                author: authorName,
                                avatar: avatar,
                                text: text.replace(/\b[A-Z]{2,}\b/g, match => match.toLowerCase()),
                                likes: likes
                            });
                        }
                    }

                    comments.sort((a, b) => b.likes - a.likes);
                    comments = comments.slice(0, 35);
                    loadingBar.style.width = '75%';

                    const postObj = { title: postTitle, channel: postChannel, thumb: postThumb, url: postUrl, id: shortcode };
                    const htmlOutput = generateBaseHTMLString(postObj, comments, AppState.year, AppState.month, AppState.day);

                    const now = new Date();
                    const yearStr = AppState.year.toString();
                    const monthStr = AppState.month.toString();
                    const dayStr = AppState.day.toString();
                    const hhmmStr = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
                    const hhmmFile = String(now.getHours()).padStart(2, '0') + String(now.getMinutes()).padStart(2, '0');
                    
                    const filename = `${yearStr}_${monthStr}_${dayStr}_${hhmmFile}_ins.html`;
                    const fileRelPath = `${yearStr}/${monthStr}/${filename}`;

                    loadingBar.style.width = '85%';
                    await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/${fileRelPath}`, {
                        method: 'PUT',
                        headers: { 'Authorization': `token ${ghToken}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Add ins post: ${postTitle.substring(0, 30)}`, content: btoa(unescape(encodeURIComponent(htmlOutput))) })
                    });

                    loadingBar.style.width = '95%';
                    const idxRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, { headers: { 'Authorization': `token ${ghToken}` } });
                    const idxData = await idxRes.json();
                    const idxContent = decodeURIComponent(escape(atob(idxData.content)));
                    
                    const dataStart = idxContent.indexOf('/*DATA_START*/') + 14;
                    const dataEnd = idxContent.indexOf('/*DATA_END*/');
                    
                    const archiveObj = JSON.parse(idxContent.substring(dataStart, dataEnd));
                    if (!archiveObj[yearStr]) archiveObj[yearStr] = {};
                    if (!archiveObj[yearStr][monthStr]) archiveObj[yearStr][monthStr] = {};
                    if (!archiveObj[yearStr][monthStr][dayStr]) archiveObj[yearStr][monthStr][dayStr] = [];
                    
                    const newItem = { time: hhmmStr, path: fileRelPath, title: `📸 ${postTitle}` };
                    archiveObj[yearStr][monthStr][dayStr].unshift(newItem);
                    
                    const newIdxContent = idxContent.substring(0, dataStart) + JSON.stringify(archiveObj) + idxContent.substring(dataEnd);
                    
                    await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, {
                        method: 'PUT',
                        headers: { 'Authorization': `token ${ghToken}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Update calendar index`, content: btoa(unescape(encodeURIComponent(newIdxContent))), sha: idxData.sha })
                    });

                    if (!archiveData[yearStr]) archiveData[yearStr] = {};
                    if (!archiveData[yearStr][monthStr]) archiveData[yearStr][monthStr] = {};
                    if (!archiveData[yearStr][monthStr][dayStr]) archiveData[yearStr][monthStr][dayStr] = [];
                    archiveData[yearStr][monthStr][dayStr].unshift(newItem);
                    
                    forceRender();
                    
                    loadingBar.style.width = '100%';
                    popToast('🎉 抓取并归档成功！', 1500);
                    this.value = '';
                    setTimeout(() => { loadingBar.style.width = '0%'; }, 1500);

                } catch (err) {
                    alert('❌ 操作失败: ' + err.message);
                    loadingBar.style.width = '0%';
                } finally { this.disabled = false; }
            }
        });

        const ENGINE_B64 = 'REPLACEME_ENGINE_B64';
        function b64DecodeUnicode(str) {
            return decodeURIComponent(atob(str).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
        }
        const engineScriptContent = b64DecodeUnicode(ENGINE_B64);

        function generateBaseHTMLString(post, comments, sYear, sMonth, sDay) {
            const pageData = {
                year: sYear, month: sMonth, day: sDay,
                post: {
                    title: post.title,
                    channel: post.channel,
                    thumb: post.thumb,
                    url: post.url,
                    now_str: `${sYear}-${String(sMonth).padStart(2,'0')}-${String(sDay).padStart(2,'0')} ${String(new Date().getHours()).padStart(2,'0')}:${String(new Date().getMinutes()).padStart(2,'0')}`
                },
                comments: comments.map(c => ({
                    author: c.author,
                    avatar: c.avatar,
                    likes_str: c.likes >= 1000 ? (c.likes / 1000).toFixed(1) + "k" : c.likes.toString(),
                    text: c.text,
                    annotation: ""
                }))
            };
            
            const pageDataStr = JSON.stringify(pageData).replace(/</g, '\\u003c');
            
            function escapeHTML(str) {
                if (typeof str !== 'string') return '';
                return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
            }

            let comments_html = "";
            pageData.comments.forEach(c => {
                comments_html += `
                <div class="chat-message">
                    <img src="${escapeHTML(c.avatar)}" class="avatar" alt="avatar" loading="lazy">
                    <div class="message-content">
                        <div class="message-header">
                            <span class="author">${escapeHTML(c.author)}</span>
                            <span class="likes">❤️ ${escapeHTML(c.likes_str)}</span>
                        </div>
                        <div class="para-wrap">
                            <div class="bubble card-text">${escapeHTML(c.text)}<span class="anno-toggle" title="点击添加/查看批注">🔴</span><span class="ai-toggle" title="AI俚语解析">🤖</span></div>
                            <div class="anno-box" style="display:none;">
                                <div class="anno-view markdown-body"></div>
                                <textarea class="anno-edit" style="display:none;" placeholder="在此记录该评论的俚语拆解或灵感...">${escapeHTML(c.annotation)}</textarea>
                            </div>
                        </div>
                    </div>
                </div>`;
            });

            return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>${escapeHTML(pageData.post.title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"><` + `/script>
    <style>
        :root { --bg: #fafafa; --card: #ffffff; --text: #262626; --muted: #8e8e8e; --accent: #d62976; --ins-btn: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%); }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; }
        .container { max-width: 600px; margin: 0 auto; padding: 0 0 50px 0; }
        .nav-back { padding: 15px; text-align: center; background: var(--card); position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 5px rgba(0,0,0,0.05); display: flex; justify-content: center; align-items: center; }
        .nav-back a { text-decoration: none; color: white; background: var(--ins-btn); padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; }
        .sync-status { padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; display: none; color: #fff; background: #2ea44f; position: absolute; right: 15px; }
        
        .post-card { background: var(--card); border-radius: 18px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.05); margin: 15px; }
        .post-thumb { width: 100%; max-height: 400px; display: block; object-fit: contain; background: #000; }
        .post-info { padding: 15px; }
        .p-channel { font-size: 0.85rem; color: var(--accent); font-weight: 700; margin-bottom: 6px; display: block; }
        .p-title { font-size: 1.05rem; font-weight: 600; margin: 0 0 12px 0; line-height: 1.4; }
        .p-actions { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #f0f0f0; padding-top: 12px; }
        .timestamp { font-size: 0.85rem; color: var(--muted); }
        .btn-play { background: #000; color: #fff; text-decoration: none; padding: 6px 14px; border-radius: 16px; font-size: 0.85rem; font-weight: 600; }
        
        .chat-container { padding: 0 15px; display: flex; flex-direction: column; gap: 15px; }
        .chat-message { display: flex; gap: 10px; align-items: flex-start; }
        .avatar { width: 36px; height: 36px; border-radius: 50%; object-fit: cover; background: #ddd; flex-shrink: 0; }
        .message-content { flex: 1; min-width: 0; }
        .message-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 4px; }
        .author { font-size: 0.85rem; color: var(--muted); font-weight: 600; }
        .likes { font-size: 0.75rem; color: var(--accent); font-weight: bold; background: #fdf0f4; padding: 2px 6px; border-radius: 8px; }
        .empty-state { text-align: center; color: var(--muted); padding: 40px 20px; }
        
        .para-wrap { width: 100%; display: flex; flex-direction: column; align-items: flex-start; }
        .bubble { background: var(--card); padding: 10px 14px; border-radius: 4px 16px 16px 16px; font-size: 0.95rem; line-height: 1.5; color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
        .anno-toggle, .ai-toggle { display: inline-block; margin-left: 8px; cursor: pointer; opacity: 0.4; font-size: 0.85rem; }
        .anno-toggle.has-anno { opacity: 1; }
        .ai-toggle.loading::after { content: "⏳"; display: inline-block; animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
        
        .anno-box { display: none; margin-top: 8px; width: 100%; box-sizing: border-box; background: #fff; border-left: 3px solid var(--accent); padding: 12px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
        .anno-view { font-size: 0.9rem; line-height: 1.5; }
        .anno-edit { width: 100%; min-height: 80px; padding: 10px; font-family: monospace; font-size: 0.9rem; border: 1px dashed #ccc; border-radius: 6px; box-sizing: border-box; display: none; }
        .markdown-body h1, .markdown-body h2, .markdown-body h3 { color: var(--accent); font-size: 1.05rem; }
    </style>
</head>
<body>
    <div class="nav-back">
        <a href="../../index.html">🔙 返回日曆樞紐</a>
        <span id="sync-status" class="sync-status"></span>
    </div>
    <div class="container">
        <h2 style="text-align: center; margin-bottom: 20px; color: #333;">📅 ${pageData.year}-${String(pageData.month).padStart(2,'0')}-${String(pageData.day).padStart(2,'0')}</h2>
        
        <div class="post-card">
            <a href="${escapeHTML(pageData.post.url)}" target="_blank"><img src="${escapeHTML(pageData.post.thumb)}" class="post-thumb" alt="Thumbnail"></a>
            <div class="post-info">
                <span class="p-channel">${escapeHTML(pageData.post.channel)}</span>
                <h1 class="p-title">${escapeHTML(pageData.post.title)}</h1>
                <div class="p-actions">
                    <span class="timestamp">更新於: ${escapeHTML(pageData.post.now_str)}</span>
                    <a href="${escapeHTML(pageData.post.url)}" target="_blank" class="btn-play">▶ 原帖</a>
                </div>
            </div>
        </div>

        <div class="chat-container">
            ${comments_html ? comments_html : '<div class="empty-state">暫无评论。</div>'}
        </div>
    </div>
    <script id="page-data" type="application/json">${pageDataStr}<` + `/script>
    <script id="matrix-engine">${engineScriptContent}<` + `/script>
</body>
</html>`;
        }
    </script>
</body>
</html>"""
    
    html_template = html_template.replace('REPLACEME_JSON_DATA', json_data)
    html_template = html_template.replace('REPLACEME_ENGINE_B64', engine_b64)
    
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_template)
    print("✅ `docs/index.html` CORS 跨域问题已修复！成功移除了 GET 请求中导致预检失败的 Content-Type。")

if __name__ == "__main__":
    generate_index_template()
