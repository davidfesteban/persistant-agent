WEB_UI = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Persistant Agents</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;color:#18181b;background:#fafafa}
main{display:grid;grid-template-columns:300px 1fr;min-height:100vh}
aside{border-right:1px solid #ddd;background:white;padding:14px}
section{padding:14px;display:grid;grid-template-rows:auto 1fr auto;gap:10px}
h1{font-size:18px;margin:0 0 10px}button,input,textarea{font:inherit}
button{border:1px solid #bbb;background:white;padding:7px 10px;cursor:pointer;border-radius:6px}
.agent{display:block;width:100%;text-align:left;margin:6px 0}.meta{color:#666;font-size:12px;overflow-wrap:anywhere}
textarea{width:100%;min-height:90px;box-sizing:border-box}input[type=text]{flex:1;min-width:0;padding:7px}
#log{background:#111;color:#f4f4f5;padding:12px;overflow:auto;white-space:pre-wrap;border-radius:6px}.row{display:flex;gap:8px;align-items:center}
</style>
</head>
<body>
<main>
<aside><div class="row"><h1>Agents</h1><button onclick="loadAgents()">Refresh</button></div><div id="agents"></div></aside>
<section>
<div><strong id="selected">Select an agent</strong><div class="meta" id="endpoint"></div></div>
<pre id="log"></pre>
<div>
<textarea id="message" placeholder="Message to Codex"></textarea>
<div class="row">
<button onclick="sendMessage()">Send</button>
<input id="filePath" type="text" placeholder="repo-relative destination">
<input id="file" type="file">
<button onclick="sendFile()">Upload</button>
</div>
</div>
</section>
</main>
<script>
let current=null, threads={};
const log=document.getElementById('log');
function write(x){log.textContent+=x+'\\n';log.scrollTop=log.scrollHeight}
async function json(url,options){const r=await fetch(url,options);const x=await r.json();if(!r.ok)throw new Error(JSON.stringify(x));return x}
async function loadAgents(){
  const data=await json('/agents'); const root=document.getElementById('agents'); root.innerHTML='';
  data.agents.forEach(agent=>{
    const b=document.createElement('button'); b.className='agent';
    b.innerHTML=`<strong>${agent.name}</strong><span class="meta">${agent.status} - ${agent.api_url||'no port'}</span>`;
    b.onclick=()=>select(agent); root.appendChild(b);
  });
}
function select(agent){current=agent;log.textContent='';document.getElementById('selected').textContent=agent.name;document.getElementById('endpoint').textContent=agent.websocket_url||''}
async function sendMessage(){
  if(!current)return write('No selected agent');
  const message=document.getElementById('message').value.trim(); if(!message)return;
  document.getElementById('message').value=''; write('> '+message);
  try{const r=await json(`/agents/${current.name}/messages`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message,thread_id:threads[current.name]})});
    threads[current.name]=r.thread_id; write(r.text||JSON.stringify(r));
  }catch(e){write(e.message)}
}
async function sendFile(){
  if(!current)return write('No selected agent');
  const file=document.getElementById('file').files[0], path=document.getElementById('filePath').value.trim();
  if(!file||!path)return write('Choose a file and destination path');
  const bytes=new Uint8Array(await file.arrayBuffer()); let bin=''; bytes.forEach(b=>bin+=String.fromCharCode(b));
  try{const r=await json(`/agents/${current.name}/files`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({files:[{path,content_base64:btoa(bin)}],thread_id:threads[current.name],message:document.getElementById('message').value.trim()||null})});
    if(r.message)threads[current.name]=r.message.thread_id; write(JSON.stringify(r,null,2));
  }catch(e){write(e.message)}
}
loadAgents();
</script>
</body>
</html>"""
