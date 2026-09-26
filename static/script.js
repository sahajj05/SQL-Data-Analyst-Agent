const messagesDiv = document.getElementById('chat-messages');
const inputField = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const threadId = 'session_' + Math.floor(Math.random() * 1000000);

function appendMessage(text, className) {
    const div = document.createElement('div');
    div.className = `message ${className}`;
    div.innerText = text;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function appendSystemNode(nodeName) {
    const div = document.createElement('div');
    div.className = `system-node-msg`;
    div.innerText = `⚙️ Processing: ${nodeName}`;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function appendInterruptBox(interruptMsg, sqlText) {
    const div = document.createElement('div');
    div.className = 'interrupt-box';
    
    const title = document.createElement('strong');
    title.innerText = '⚠️ Approval Required';
    
    const pre = document.createElement('pre');
    pre.innerText = sqlText || 'No SQL generated.';
    
    const text = document.createElement('div');
    text.innerText = interruptMsg;
    text.style.fontSize = '0.9em';
    text.style.marginTop = '10px';

    const btnRow = document.createElement('div');
    btnRow.className = 'btn-row';

    const rejectBtn = document.createElement('button');
    rejectBtn.className = 'btn btn-reject';
    rejectBtn.innerText = 'Reject';
    rejectBtn.onclick = () => submitResume('no', div);

    const approveBtn = document.createElement('button');
    approveBtn.className = 'btn btn-approve';
    approveBtn.innerText = 'Approve';
    approveBtn.onclick = () => submitResume('yes', div);

    btnRow.appendChild(rejectBtn);
    btnRow.appendChild(approveBtn);

    div.appendChild(title);
    div.appendChild(pre);
    div.appendChild(text);
    div.appendChild(btnRow);

    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function handleKeyPress(e) {
    if (e.key === 'Enter') sendQuery();
}

async function handleStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    let buffer = "";
    
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        let lines = buffer.split('\n\n');
        
        buffer = lines.pop(); 
        
        for (let line of lines) {
            if (line.startsWith('data: ')) {
                const data = JSON.parse(line.substring(6));
                
                if (data.node) {
                    appendSystemNode(data.node);
                }
                if (data.answer) {
                    appendMessage(data.answer, 'agent-msg');
                }
                if (data.interrupt) {
                    let parts = data.interrupt.split('\n\n');
                    appendInterruptBox('Do you approve this execution?', parts[0]);
                }
            }
        }
    }
    
    inputField.disabled = false;
    sendBtn.disabled = false;
}

async function sendQuery() {
    const query = inputField.value.trim();
    if (!query) return;

    appendMessage(query, 'user-msg');
    inputField.value = '';
    
    inputField.disabled = true;
    sendBtn.disabled = true;

    const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query, thread_id: threadId })
    });

    handleStream(response);
}

async function submitResume(action, boxElement) {
    const buttons = boxElement.querySelectorAll('button');
    buttons.forEach(btn => btn.disabled = true);
    
    const status = document.createElement('div');
    status.innerText = `You selected: ${action.toUpperCase()}`;
    status.style.marginTop = '10px';
    status.style.fontWeight = 'bold';
    boxElement.appendChild(status);

    const response = await fetch('/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action, thread_id: threadId })
    });

    handleStream(response);
}

document.addEventListener('DOMContentLoaded', fetchSchema);

async function fetchSchema() {
    try {
        const response = await fetch('/schema');
        const data = await response.json();
        
        if (data.error) {
            console.error("Error fetching schema:", data.error);
            document.getElementById('db-schema-tree').innerHTML = `<div style="padding: 20px; color: red;">Failed to load schema.</div>`;
            return;
        }
        
        renderSidebar(data.tables);
    } catch (err) {
        console.error("Failed to load schema:", err);
    }
}

function renderSidebar(tables) {
    const container = document.getElementById('db-schema-tree');
    container.innerHTML = '';
    
    tables.forEach(table => {
        const tableDiv = document.createElement('div');
        
        const tableHeader = document.createElement('div');
        tableHeader.className = 'tree-table';
        tableHeader.innerText = table.name;
        
        const columnsDiv = document.createElement('div');
        columnsDiv.className = 'tree-columns';
        
        table.columns.forEach(col => {
            const colDiv = document.createElement('div');
            colDiv.className = 'tree-column';
            colDiv.innerHTML = `<span>${col.name}</span> <span class="type-badge">${col.type}</span>`;
            columnsDiv.appendChild(colDiv);
        });
        
        tableHeader.onclick = () => {
            tableHeader.classList.toggle('open');
            columnsDiv.classList.toggle('open');
        };
        
        tableDiv.appendChild(tableHeader);
        tableDiv.appendChild(columnsDiv);
        container.appendChild(tableDiv);
    });
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('mobile-open');
}
