const API = (window.VOICELAB_API_BASE || '').replace(/\/$/, '');
const assetUrl = (url='') => (url && url.startsWith('/') && API ? API + url : url);
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = (s='') => String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const state = {
  page:'voice', voices:[], catalog:[], liveVoices:[], selectedVoice:'', uploadFile:null,
  recorder:null, chunks:[], favorites:new Set(), voiceFavorites:new Set(), jobs:[],
  token:localStorage.getItem('voicelab_token')||'', user:null, editorUrl:'', compareJobs:[]
};

async function api(path, init={}) {
  init={...init,headers:{...(init.headers||{})}};
  if(state.token) init.headers.Authorization=`Bearer ${state.token}`;
  const r = await fetch(API+path, init);
  let data = null;
  const ct = r.headers.get('content-type') || '';
  if (ct.includes('application/json')) data = await r.json();
  if (!r.ok) throw new Error(data?.detail || r.statusText || 'Request failed');
  return data;
}

const icons={voice:'◉',character:'✦',licensed:'★',marketplace:'◈',cover:'♫',sfx:'⌁',isolate:'✂',remove:'⊘',extract:'⇩',library:'＋',compare:'⇄',editor:'✎',queue:'⌛',history:'↺',account:'●',admin:'▣',settings:'⚙'};
const nav=[
  ['voice','AI Voice'],['character','Character Voice'],['licensed','Licensed Voice'],['marketplace','Marketplace'],['cover','AI Cover'],['sfx','Sound Effects'],
  ['isolate','Vocal Isolator'],['remove','Vocal Remover'],['extract','Audio Extractor'],['library','Voice Library'],['compare','A/B Compare'],['editor','Audio Editor'],['queue','Queue'],['history','History'],['account','Account'],['admin','Admin'],['settings','Settings']
];

function layout(content){
  const activeJobs=state.jobs.filter(j=>j.status==='queued'||j.status==='running').length;
  return `<div class="app-shell"><aside>
    <div class="brand"><div class="logo">◒</div><div><b>VoiceLab</b><small>Studio</small></div></div>
    <nav>${nav.filter(([id])=>id!=='admin'||state.user?.is_admin).map(([id,label])=>`<button data-nav="${id}" class="${state.page===id?'active':''}"><span>${icons[id]}</span>${label}${id==='queue'&&activeJobs?`<em>${activeJobs}</em>`:''}</button>`).join('')}</nav>
    <div class="side-note"><b>${state.user?esc(state.user.display_name):'Local workspace'}</b><span>${state.user?esc(state.user.email):'Sign in to enable cloud uploads.'}</span></div>
  </aside><main>${content}</main></div>`;
}
function bindNav(){ $$('[data-nav]').forEach(b=>b.onclick=()=>{state.page=b.dataset.nav;render();}); }
function hero(title,desc,pill=''){return `<div class="hero">${pill?`<span class="pill">${esc(pill)}</span>`:''}<h1>${esc(title)}</h1><p>${esc(desc)}</p></div>`}
function notice(t){return `<div class="notice">${t}</div>`}
function errorBox(t){return `<div class="error">${esc(t)}</div>`}
function fmtDate(x){try{return new Date(x).toLocaleString()}catch{return x||''}}
function fileNameFromPath(path=''){return String(path).split(/[\\/]/).pop()}

function audioResult(url, disclosure='AI-generated audio'){
  const id='wave_'+Math.random().toString(36).slice(2);
  return `<div class="result rich-result"><div class="wave-player"><canvas id="${id}" data-wave-url="${esc(assetUrl(url))}" class="waveform" width="720" height="90"></canvas><audio controls src="${esc(assetUrl(url))}"></audio></div><a class="btn secondary" href="${esc(assetUrl(url))}" download>Download</a><span class="ai-tag">${esc(disclosure)}</span></div>`;
}
async function drawWave(canvas){
  if(!canvas||canvas.dataset.drawn)return;
  canvas.dataset.drawn='1';
  const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);ctx.strokeStyle='#716f86';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
  try{
    const res=await fetch(canvas.dataset.waveUrl);const buf=await res.arrayBuffer();
    const ac=new (window.AudioContext||window.webkitAudioContext)();const audio=await ac.decodeAudioData(buf.slice(0));
    const data=audio.getChannelData(0),bars=180,step=Math.max(1,Math.floor(data.length/bars));
    ctx.clearRect(0,0,w,h);ctx.fillStyle='#8b63ff';
    for(let i=0;i<bars;i++){
      let peak=0,start=i*step,end=Math.min(data.length,start+step);
      for(let j=start;j<end;j+=Math.max(1,Math.floor(step/64)))peak=Math.max(peak,Math.abs(data[j]));
      const bh=Math.max(2,peak*(h-10));const x=i*(w/bars);ctx.fillRect(x,(h-bh)/2,Math.max(1,w/bars-2),bh);
    }
    ac.close();
  }catch{}
}
function hydrateWaveforms(root=document){$$('canvas[data-wave-url]',root).forEach(drawWave)}

async function loadFavorites(){
  const rows=await api('/api/favorites').catch(()=>[]);
  state.favorites=new Set(rows.filter(x=>x.item_type==='catalog').map(x=>x.item_id));
  state.voiceFavorites=new Set(rows.filter(x=>x.item_type==='voice').map(x=>x.item_id));
}
async function toggleFavorite(type,id,button){
  const set=type==='catalog'?state.favorites:state.voiceFavorites;const favorite=!set.has(id);
  await api('/api/favorites',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_type:type,item_id:id,favorite})});
  favorite?set.add(id):set.delete(id);if(button){button.classList.toggle('on',favorite);button.textContent=favorite?'★':'☆'}
}

function filteredVoices(mode,q='',capability='tts'){
  return state.voices.filter(v=>(mode==='all'||mode==='studio'?mode==='all'||v.category==='studio':v.category===mode)&&(!capability||(v.capabilities||[]).includes(capability))&&v.name.toLowerCase().includes(q.toLowerCase()));
}
function voiceCards(items){
  return items.map(v=>`<div class="voice-card ${v.id===state.selectedVoice?'selected':''}" data-voice-wrap="${esc(v.id)}">
    <button class="voice-main" data-voice="${esc(v.id)}"><div class="avatar">${esc(v.name[0]||'?')}</div><div><b>${esc(v.name)}</b><small>${esc(v.gender||'Voice')} · ${esc(v.provider)}</small></div><span>▶</span></button>
    <button class="fav-btn ${state.voiceFavorites.has(v.id)?'on':''}" data-fav-voice="${esc(v.id)}" title="Favorite">${state.voiceFavorites.has(v.id)?'★':'☆'}</button>
  </div>`).join('') || `<div class="notice full">No voices in this category yet.</div>`;
}
function voicePicker(mode){
  const items=filteredVoices(mode);
  if(!state.selectedVoice || !items.some(v=>v.id===state.selectedVoice)) state.selectedVoice=items[0]?.id || '';
  return `<div class="search"><span>⌕</span><input id="voiceSearch" placeholder="Search voices"></div><div class="voice-grid" id="voiceGrid">${voiceCards(items)}</div>`;
}
function bindVoiceButtons(){
  $$('[data-voice]').forEach(b=>b.onclick=()=>{state.selectedVoice=b.dataset.voice;$$('[data-voice-wrap]').forEach(x=>x.classList.toggle('selected',x.dataset.voiceWrap===state.selectedVoice));});
  $$('[data-fav-voice]').forEach(b=>b.onclick=async e=>{e.stopPropagation();await toggleFavorite('voice',b.dataset.favVoice,b);});
}
function bindVoicePicker(mode){
  const search=$('#voiceSearch'); if(search)search.oninput=()=>{$('#voiceGrid').innerHTML=voiceCards(filteredVoices(mode,search.value));bindVoiceButtons();};bindVoiceButtons();
}

function jobProgress(job){
  const p=Math.max(0,Math.min(100,job.progress||0));
  return `<div class="job-box ${esc(job.status)}" data-job-box="${esc(job.id)}"><div class="job-top"><div><b>${esc(job.title)}</b><small>${esc(job.phase||job.status)}</small></div><span>${p}%</span></div><div class="progress"><i style="width:${p}%"></i></div>${job.error?errorBox(job.error):''}${job.output_url?audioResult(job.output_url):''}</div>`;
}
async function pollJob(jobId, target, button=null, idleText='Generate'){
  let done=false;
  while(!done){
    const job=await api('/api/jobs/'+jobId);const idx=state.jobs.findIndex(x=>x.id===job.id);if(idx>=0)state.jobs[idx]=job;else state.jobs.unshift(job);
    target.innerHTML=jobProgress(job);hydrateWaveforms(target);
    done=job.status==='completed'||job.status==='failed';if(!done)await new Promise(r=>setTimeout(r,900));
  }
  if(button){button.disabled=false;button.textContent=idleText;}
}
async function startJsonJob(path,payload,target,button,idleText){
  button.disabled=true;button.textContent='Queued…';target.innerHTML='';
  try{const job=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.jobs.unshift(job);target.innerHTML=jobProgress(job);pollJob(job.id,target,button,idleText)}catch(e){target.innerHTML=errorBox(e.message);button.disabled=false;button.textContent=idleText}
}
async function startFormJob(path,fd,target,button,idleText){
  button.disabled=true;button.textContent='Queued…';target.innerHTML='';
  try{const job=await api(path,{method:'POST',body:fd});state.jobs.unshift(job);target.innerHTML=jobProgress(job);pollJob(job.id,target,button,idleText)}catch(e){target.innerHTML=errorBox(e.message);button.disabled=false;button.textContent=idleText}
}

function ttsPage(mode,title){
  return layout(`<div class="tool-page">${hero(title,'Choose a voice, type your script, tune delivery, then generate and download audio.','Voice generator')}
  <div class="panel"><h3>Listen & pick an AI voice</h3>${voicePicker(mode)}
    <div class="editor"><div class="prompt-row"><button data-prompt="Hey there! Thanks for stopping by. I hope your day is going great.">Greetings</button><button data-prompt="I cannot believe it! This is absolutely amazing!">Emotions</button><button data-prompt="Take one step forward, turn left, and open the door.">Actions</button><button data-prompt="Once upon a time, beyond the hills, a small town waited for an unlikely hero.">Stories</button></div><textarea id="ttsText" maxlength="4096">Welcome to VoiceLab Studio. This is an AI-generated voice preview.</textarea><span class="count" id="count">68/4096</span></div>
    <div class="settings-grid"><label><span>Volume <b id="volLabel">0</b> dB</span><input id="volume" type="range" min="-6" max="6" value="0"></label><label><span>Speed <b id="speedLabel">1.0</b>×</span><input id="speed" type="range" min="0.5" max="2" value="1" step="0.1"></label><label><span>Emotion</span><select id="emotion"><option>neutral</option><option>cheerful</option><option>sad</option><option>excited</option><option>calm</option><option>dramatic</option><option>angry</option></select></label><label><span>Emotion intensity <b id="intensityLabel">50</b>%</span><input id="intensity" type="range" min="0" max="100" value="50"></label></div>
    <button class="btn primary wide" id="generateTTS">Generate</button><div id="toolMessage"></div>
    ${mode!=='studio'?`<div class="subtool"><h3>Voice-to-voice converter</h3><p>Upload or record speech and convert it with an authorized ElevenLabs or Kits voice.</p><label><span>Conversion voice</span><select id="convertVoiceSelect">${filteredVoices(mode,'','voice_conversion').map(v=>`<option value="${esc(v.id)}">${esc(v.name)} · ${esc(v.provider)}</option>`).join('')}</select></label>${uploadBox('audio/*')}<button class="btn secondary wide" id="convertVoice">Convert recording</button><div id="convertMessage"></div></div>`:''}
    ${notice('Only use built-in voices or voices you own, license, or have permission to use. Disclose generated speech as AI-generated when you share it.')}
  </div></div>`);
}
function bindTTS(mode){
  bindNav();bindVoicePicker(mode);if(mode!=='studio')bindUpload();
  const txt=$('#ttsText'),count=$('#count');txt.oninput=()=>count.textContent=`${txt.value.length}/4096`;
  $$('[data-prompt]').forEach(b=>b.onclick=()=>{txt.value=b.dataset.prompt;txt.dispatchEvent(new Event('input'));});
  $('#volume').oninput=e=>$('#volLabel').textContent=e.target.value;$('#speed').oninput=e=>$('#speedLabel').textContent=Number(e.target.value).toFixed(1);$('#intensity').oninput=e=>$('#intensityLabel').textContent=e.target.value;
  $('#generateTTS').onclick=()=>startJsonJob('/api/jobs/tts',{text:txt.value,voice_id:state.selectedVoice,volume_db:+$('#volume').value,speed:+$('#speed').value,emotion:$('#emotion').value,emotion_intensity:+$('#intensity').value},$('#toolMessage'),$('#generateTTS'),'Generate');
  const cv=$('#convertVoice');if(cv)cv.onclick=()=>{const file=state.uploadFile;if(!file){$('#convertMessage').innerHTML=errorBox('Choose or record an audio file first.');return;}const fd=new FormData();fd.append('file',file);fd.append('voice_id',$('#convertVoiceSelect')?.value||state.selectedVoice);startFormJob('/api/jobs/voice-convert',fd,$('#convertMessage'),cv,'Convert recording');};
}

function uploadBox(accept='audio/*,video/*'){return `<div class="upload-wrap"><label class="drop"><span class="upload-icon">⇧</span><strong id="fileName">Drop a file here or click to browse</strong><span>MP3, WAV, M4A, FLAC, AAC, OGG, MP4, MOV · up to 20 MB</span><input hidden id="fileInput" type="file" accept="${accept}"></label><button type="button" class="btn secondary record-btn" id="recordBtn">● Record microphone</button></div>`}
function bindUpload(){state.uploadFile=null;const f=$('#fileInput');f.onchange=()=>{state.uploadFile=f.files?.[0]||null;$('#fileName').textContent=state.uploadFile?.name||'Drop a file here or click to browse';};const rb=$('#recordBtn');if(!rb)return;rb.onclick=async()=>{if(state.recorder?.state==='recording'){state.recorder.stop();rb.textContent='● Record microphone';return;}try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});state.chunks=[];const rec=new MediaRecorder(stream);state.recorder=rec;rec.ondataavailable=e=>{if(e.data.size)state.chunks.push(e.data)};rec.onstop=()=>{const blob=new Blob(state.chunks,{type:rec.mimeType||'audio/webm'});state.uploadFile=new File([blob],'microphone-recording.webm',{type:blob.type});$('#fileName').textContent=state.uploadFile.name;stream.getTracks().forEach(t=>t.stop());};rec.start();rb.textContent='■ Stop recording'}catch(e){alert('Microphone access failed: '+e.message)}}}

function fileTool(kind,title,desc,button){return layout(`<div class="tool-page">${hero(title,desc)}<div class="panel">${uploadBox()}<button class="btn primary wide" id="fileGo">${button}</button><div id="toolMessage"></div></div></div>`)}
function bindFileTool(kind,buttonText){bindNav();bindUpload();$('#fileGo').onclick=()=>{const file=state.uploadFile;if(!file){$('#toolMessage').innerHTML=errorBox('Choose a file first.');return;}const fd=new FormData();fd.append('file',file);if(kind==='extract')fd.append('format','mp3');startFormJob('/api/jobs/audio/'+kind,fd,$('#toolMessage'),$('#fileGo'),buttonText);};}

function sfxPage(){const presets=['Sword whoosh','Ocean waves','Glass shattering','Magic spell','Piano sting','Baby laughing','Typing in a quiet office','Noisy restaurant','Doorbell'];return layout(`<div class="tool-page">${hero('AI Sound Effect Generator','Turn a text description into a production-ready sound effect.')}<div class="panel"><div class="prompt-row">${presets.map(p=>`<button data-sfx="${esc(p)}">${esc(p)}</button>`).join('')}</div><textarea id="sfxPrompt" maxlength="500">Cinematic thunder rolling across a distant mountain valley</textarea><label class="slider-line">Duration <b id="durLabel">5</b>s<input id="duration" type="range" min="1" max="22" value="5"></label><button class="btn primary wide" id="sfxGo">Generate sound</button><div id="toolMessage"></div></div></div>`)}
function bindSfx(){bindNav();$$('[data-sfx]').forEach(b=>b.onclick=()=>$('#sfxPrompt').value=b.dataset.sfx);$('#duration').oninput=e=>$('#durLabel').textContent=e.target.value;$('#sfxGo').onclick=()=>startJsonJob('/api/jobs/sfx',{prompt:$('#sfxPrompt').value,duration_seconds:+$('#duration').value},$('#toolMessage'),$('#sfxGo'),'Generate sound');}

function coverPage(){const eligible=state.voices.filter(v=>(v.capabilities||[]).includes('voice_conversion')&&v.category!=='studio');if(!state.selectedVoice||!eligible.some(v=>v.id===state.selectedVoice))state.selectedVoice=eligible[0]?.id||'';return layout(`<div class="tool-page">${hero('AI Cover','Separate vocals, convert them to an authorized target voice, transpose the vocal if needed, then remix with level control.','Advanced cover mix')}<div class="panel"><h3>Choose an authorized conversion voice</h3>${eligible.length?`<div class="voice-grid">${voiceCards(eligible)}</div>`:notice('Add an authorized ElevenLabs or Kits conversion voice in Voice Library first.')} ${uploadBox()}<div class="settings-grid cover-controls"><label><span>Key / pitch <b id="pitchLabel">0</b> semitones</span><input id="coverPitch" type="range" min="-12" max="12" step="1" value="0"></label><label><span>Converted vocal <b id="vocalGainLabel">0</b> dB</span><input id="vocalGain" type="range" min="-12" max="6" step="1" value="0"></label><label><span>Instrumental <b id="instGainLabel">0</b> dB</span><input id="instGain" type="range" min="-12" max="6" step="1" value="0"></label></div><button class="btn primary wide" id="coverGo">Create cover</button><div id="toolMessage"></div>${notice('Pitch is applied locally after conversion, so it works with both ElevenLabs and Kits. Use only source audio and target voices you are authorized to process.')}</div></div>`)}
function bindCover(){bindNav();bindVoiceButtons();bindUpload();$('#coverPitch').oninput=e=>$('#pitchLabel').textContent=e.target.value;$('#vocalGain').oninput=e=>$('#vocalGainLabel').textContent=e.target.value;$('#instGain').oninput=e=>$('#instGainLabel').textContent=e.target.value;$('#coverGo').onclick=()=>{const file=state.uploadFile;if(!file||!state.selectedVoice){$('#toolMessage').innerHTML=errorBox('Choose a file and conversion voice first.');return;}const fd=new FormData();fd.append('file',file);fd.append('voice_id',state.selectedVoice);fd.append('pitch_semitones',$('#coverPitch').value);fd.append('vocal_gain_db',$('#vocalGain').value);fd.append('instrumental_gain_db',$('#instGain').value);startFormJob('/api/jobs/cover',fd,$('#toolMessage'),$('#coverGo'),'Create cover');};}
function bindLibrary(){bindNav();bindVoiceButtons();$('#addVoice').onclick=async()=>{const m=$('#toolMessage');m.innerHTML='';try{await api('/api/voices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('#vName').value,category:$('#vCategory').value,provider:$('#vProvider').value,provider_voice_id:$('#vId').value,gender:$('#vGender').value,description:$('#vDesc').value,authorized:$('#vAuth').checked})});await loadVoices();m.innerHTML=notice('Voice added.');}catch(e){m.innerHTML=errorBox(e.message)}}}

function catalogCard(x){
  const caps=(x.capabilities||[]).map(c=>`<span class="mini-pill">${esc(c.replaceAll('_',' '))}</span>`).join('');
  const access=x.access==='request_license'?'Approval required':x.access==='provider_account'?'Provider account':x.access==='enterprise'?'Enterprise':'Available';
  const fav=state.favorites.has(x.id);
  return `<article class="catalog-card" data-id="${esc(x.id)}" data-provider="${esc(x.provider)}" data-access="${esc(x.access)}" data-kind="${esc(x.kind)}" data-caps="${esc((x.capabilities||[]).join(' '))}" data-name="${esc(x.name.toLowerCase())}" data-search="${esc((x.name+' '+x.provider+' '+x.description+' '+x.kind).toLowerCase())}" data-favorite="${fav?'1':'0'}">
    <button class="fav-btn catalog-fav ${fav?'on':''}" data-fav-catalog="${esc(x.id)}" title="Favorite">${fav?'★':'☆'}</button>
    <div class="catalog-head"><div class="avatar">${esc(x.name[0]||'?')}</div><div><b>${esc(x.name)}</b><small>${esc(x.provider)} · ${esc(x.kind.replaceAll('_',' '))}</small></div></div>
    <p>${esc(x.description||'')}</p><div class="caps">${caps}</div>
    <div class="catalog-foot"><span class="access ${esc(x.access)}">${esc(access)}</span>${x.source_url?`<a class="btn secondary compact" href="${esc(x.source_url)}" target="_blank" rel="noreferrer">Provider</a>`:''}</div>
  </article>`;
}
async function marketplacePage(){
  if(!state.catalog.length)state.catalog=await api('/api/catalog').catch(()=>[]);
  const providers=[...new Set(state.catalog.map(x=>x.provider))].sort();const kinds=[...new Set(state.catalog.map(x=>x.kind))].sort();
  return layout(`<div class="tool-page">${hero('Voice Marketplace','Browse researched licensed, verified, and rights-holder-approved voice sources. Favorite promising voices and sync providers you actually subscribe to.',`${state.catalog.length} researched entries`)}
  <div class="stats-row"><div><b>${state.catalog.length}</b><span>Catalog entries</span></div><div><b>${providers.length}</b><span>Providers</span></div><div><b>${state.favorites.size}</b><span>Favorites</span></div><div><b>${state.voices.length}</b><span>Usable voices</span></div></div>
  <div class="panel"><div class="catalog-toolbar advanced"><div class="search"><span>⌕</span><input id="catalogSearch" placeholder="Search celebrity, character, artist, provider…"></div><select id="catalogProvider"><option value="">All providers</option>${providers.map(x=>`<option>${esc(x)}</option>`).join('')}</select><select id="catalogKind"><option value="">All types</option>${kinds.map(x=>`<option value="${esc(x)}">${esc(x.replaceAll('_',' '))}</option>`).join('')}</select><select id="catalogAccess"><option value="">All access</option><option value="provider_account">Provider account</option><option value="request_license">Approval required</option><option value="enterprise">Enterprise</option></select><select id="catalogCap"><option value="">All capabilities</option><option value="tts">TTS</option><option value="voice_conversion">Voice conversion</option><option value="singing">Singing</option><option value="project_delivery">Project delivery</option></select><select id="catalogSort"><option value="name">Name A–Z</option><option value="provider">Provider</option><option value="favorites">Favorites first</option></select><label class="filter-check"><input id="catalogFavOnly" type="checkbox"> Favorites only</label></div><div class="filter-summary"><span id="catalogCount">${state.catalog.length}</span> voices shown</div><div class="catalog-grid" id="catalogGrid">${state.catalog.map(catalogCard).join('')}</div></div>
  <div class="panel live-panel"><h3>Live provider sync</h3><p class="muted">Query your configured provider account and import voices you are authorized to use. Keys remain server-side.</p><div class="live-actions"><button class="btn secondary" id="syncEleven">Sync ElevenLabs</button><button class="btn secondary" id="syncRespeecher">Sync Respeecher</button><button class="btn secondary" id="syncSpeechify">Sync Speechify</button><button class="btn secondary" id="syncKits">Sync Kits</button></div><div id="liveMessage"></div><div id="liveResults" class="live-results"></div></div></div>`);
}
function applyCatalogFilters(){
  const q=($('#catalogSearch')?.value||'').toLowerCase(),p=$('#catalogProvider')?.value||'',k=$('#catalogKind')?.value||'',a=$('#catalogAccess')?.value||'',c=$('#catalogCap')?.value||'',fav=$('#catalogFavOnly')?.checked,sort=$('#catalogSort')?.value||'name';
  const grid=$('#catalogGrid');let cards=$$('.catalog-card',grid);let shown=0;
  cards.forEach(card=>{const hidden=!!((q&&!card.dataset.search.includes(q))||(p&&card.dataset.provider!==p)||(k&&card.dataset.kind!==k)||(a&&card.dataset.access!==a)||(c&&!card.dataset.caps.split(' ').includes(c))||(fav&&card.dataset.favorite!=='1'));card.hidden=hidden;if(!hidden)shown++;});
  cards.sort((x,y)=>sort==='provider'?x.dataset.provider.localeCompare(y.dataset.provider)||x.dataset.name.localeCompare(y.dataset.name):sort==='favorites'?(+y.dataset.favorite)-(+x.dataset.favorite)||x.dataset.name.localeCompare(y.dataset.name):x.dataset.name.localeCompare(y.dataset.name)).forEach(x=>grid.appendChild(x));
  if($('#catalogCount'))$('#catalogCount').textContent=shown;
}
function renderLiveEleven(data){const voices=data.voices||[];state.liveVoices=voices;if(!voices.length)return notice('No voices returned for this account/filter.');return `<div class="live-list">${voices.map((v,i)=>`<div class="live-row"><div><b>${esc(v.name)}</b><small>${esc(v.language||'')} ${esc(v.accent||'')} · ${esc(v.category||'shared')}</small><p>${esc(v.description||'')}</p></div><div class="live-controls">${v.preview_url?`<audio controls preload="none" src="${esc(v.preview_url)}"></audio>`:''}<button class="btn primary compact" data-import-eleven="${i}">Add</button></div></div>`).join('')}</div>`}
function renderLiveSpeechify(data){const voices=data.voices||[];state.liveVoices=voices;if(!voices.length)return notice('No Speechify voices returned.');return `<div class="live-list">${voices.map((v,i)=>`<div class="live-row"><div><b>${esc(v.display_name||v.id)}</b><small>${esc(v.gender||'')} · ${esc(v.locale||'')} · ${esc(v.type||'shared')}</small></div><div class="live-controls">${v.preview_audio?`<audio controls preload="none" src="${esc(v.preview_audio)}"></audio>`:''}<button class="btn primary compact" data-import-speechify="${i}">Add</button></div></div>`).join('')}</div>`}
function renderLiveKits(data){const voices=data.data||[];state.liveVoices=voices;if(!voices.length)return notice('No Kits voice models returned.');return `<div class="live-list">${voices.map((v,i)=>`<div class="live-row"><div><b>${esc(v.title||v.id)}</b><small>Kits model · ${(v.tags||[]).slice(0,4).map(esc).join(' · ')}</small></div><div class="live-controls">${v.demoUrl?`<audio controls preload="none" src="${esc(v.demoUrl)}"></audio>`:''}<button class="btn primary compact" data-import-kits="${i}">Add</button></div></div>`).join('')}</div>`}
function renderLiveRespeecher(voices){state.liveVoices=voices||[];if(!state.liveVoices.length)return notice('No Respeecher voices returned.');return `<div class="live-list">${state.liveVoices.map((v,i)=>`<div class="live-row"><div><b>${esc(v.name||v.id)}</b><small>${esc(v.gender||'')} · ${esc(v.accent||'')}</small></div><button class="btn primary compact" data-import-respeecher="${i}">Add</button></div>`).join('')}</div>`}
function bindMarketplace(){
  bindNav();['#catalogSearch','#catalogProvider','#catalogKind','#catalogAccess','#catalogCap','#catalogSort','#catalogFavOnly'].forEach(sel=>{const el=$(sel);if(el)el.oninput=applyCatalogFilters;});
  $$('[data-fav-catalog]').forEach(b=>b.onclick=async()=>{await toggleFavorite('catalog',b.dataset.favCatalog,b);const card=b.closest('.catalog-card');card.dataset.favorite=state.favorites.has(b.dataset.favCatalog)?'1':'0';applyCatalogFilters();});
  applyCatalogFilters();const msg=$('#liveMessage'),out=$('#liveResults');
  const sync=async(btn,path,renderer,label)=>{btn.disabled=true;msg.innerHTML=notice(`Querying ${label}…`);out.innerHTML='';try{const data=await api(path);msg.innerHTML='';out.innerHTML=renderer(data);bindLiveImports();}catch(e){msg.innerHTML=errorBox(e.message)}finally{btn.disabled=false}};
  $('#syncEleven').onclick=()=>sync($('#syncEleven'),'/api/catalog/live/elevenlabs?category=professional&page_size=50',renderLiveEleven,'ElevenLabs');
  $('#syncRespeecher').onclick=()=>sync($('#syncRespeecher'),'/api/catalog/live/respeecher',renderLiveRespeecher,'Respeecher');
  $('#syncSpeechify').onclick=()=>sync($('#syncSpeechify'),'/api/catalog/live/speechify?locale=en&limit=100',renderLiveSpeechify,'Speechify');
  $('#syncKits').onclick=()=>sync($('#syncKits'),'/api/catalog/live/kits?per_page=50',renderLiveKits,'Kits');
}
function bindLiveImports(){
  $$('[data-import-eleven]').forEach(b=>b.onclick=async()=>{const v=state.liveVoices[+b.dataset.importEleven];b.disabled=true;try{await api('/api/catalog/import/elevenlabs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({public_owner_id:v.public_owner_id,voice_id:v.voice_id,name:v.name,category:'custom',gender:v.gender||'',description:v.description||'Imported verified ElevenLabs shared voice'})});await loadVoices();b.textContent='Added ✓';}catch(e){b.disabled=false;alert(e.message)}});
  $$('[data-import-respeecher]').forEach(b=>b.onclick=async()=>{const v=state.liveVoices[+b.dataset.importRespeecher];b.disabled=true;try{await api('/api/catalog/import/respeecher',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voice_id:v.id,name:v.name||v.id,category:'licensed',gender:v.gender||'',description:`Licensed Respeecher voice${v.accent?' · '+v.accent:''}`})});await loadVoices();b.textContent='Added ✓';}catch(e){b.disabled=false;alert(e.message)}});
  $$('[data-import-speechify]').forEach(b=>b.onclick=async()=>{const v=state.liveVoices[+b.dataset.importSpeechify];b.disabled=true;try{await api('/api/catalog/import/speechify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voice_id:v.id,name:v.display_name||v.id,category:'licensed',gender:v.gender||'',description:`Speechify shared voice${v.locale?' · '+v.locale:''}`})});await loadVoices();b.textContent='Added ✓';}catch(e){b.disabled=false;alert(e.message)}});
  $$('[data-import-kits]').forEach(b=>b.onclick=async()=>{const v=state.liveVoices[+b.dataset.importKits];b.disabled=true;try{await api('/api/catalog/import/kits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voice_id:String(v.id),name:v.title||String(v.id),category:'licensed',gender:'',description:`Kits voice model${(v.tags||[]).length?' · '+v.tags.slice(0,4).join(', '):''}`})});await loadVoices();b.textContent='Added ✓';}catch(e){b.disabled=false;alert(e.message)}});
}

async function queuePage(){state.jobs=await api('/api/jobs?limit=50').catch(()=>[]);return layout(`<div class="tool-page">${hero('Generation Queue','Track real server-side jobs while you keep using the rest of the studio.',`${state.jobs.filter(j=>j.status==='queued'||j.status==='running').length} active`)}<div class="panel"><div class="queue-list">${state.jobs.length?state.jobs.map(jobProgress).join(''):notice('No queued jobs yet. Start a generation or audio tool and it will appear here.')}</div></div></div>`)}
async function watchQueueJob(jobId){
  while(true){
    const job=await api('/api/jobs/'+jobId);const idx=state.jobs.findIndex(x=>x.id===job.id);if(idx>=0)state.jobs[idx]=job;
    const box=$(`[data-job-box="${jobId}"]`);if(box){box.outerHTML=jobProgress(job);const fresh=$(`[data-job-box="${jobId}"]`);if(fresh)hydrateWaveforms(fresh);}
    if(job.status==='completed'||job.status==='failed')break;await new Promise(r=>setTimeout(r,1000));
  }
}
function bindQueue(){bindNav();hydrateWaveforms();state.jobs.filter(j=>j.status==='queued'||j.status==='running').forEach(j=>watchQueueJob(j.id));}

async function historyPage(){
  const items=await api('/api/history?limit=100').catch(()=>[]);
  return layout(`<div class="tool-page">${hero('History','Persistent local history with editing, sharing, and optional cloud mirroring.',`${items.length} recent items`)}<div class="panel"><div class="history-list rich-history">${items.length?items.map(i=>{const url=i.output_path?`/api/files/${encodeURIComponent(fileNameFromPath(i.output_path))}`:'';return `<div class="history-item"><div class="history-meta"><b>${esc(i.title)}</b><small>${fmtDate(i.created_at)} · ${esc(i.tool)}</small>${i.metadata?.voice?`<span>${esc(i.metadata.voice)}</span>`:''}</div>${url?`<div class="history-audio"><canvas data-wave-url="${assetUrl(url)}" class="waveform mini" width="420" height="54"></canvas><audio controls preload="none" src="${assetUrl(url)}"></audio><div class="history-actions"><button class="btn ghost compact" data-edit-url="${url}">Edit</button><button class="btn ghost compact" data-share-url="${url}" data-share-title="${esc(i.title)}">Share</button>${state.user?`<button class="btn ghost compact" data-cloud-url="${url}">Cloud</button>`:''}<a class="btn secondary compact" href="${assetUrl(url)}" download>Download</a></div></div>`:''}</div>`}).join(''):notice('No generations yet.')}</div></div></div>`)
}
function bindHistory(){bindNav();hydrateWaveforms();$$('[data-edit-url]').forEach(b=>b.onclick=()=>{state.editorUrl=b.dataset.editUrl;state.page='editor';render();});$$('[data-share-url]').forEach(b=>b.onclick=async()=>{try{const x=await api('/api/shares',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({output_url:b.dataset.shareUrl,title:b.dataset.shareTitle})});const url=new URL(x.share_url,(API||location.origin)+'/').href;await navigator.clipboard?.writeText(url);b.textContent='Link copied ✓';}catch(e){alert(e.message)}});$$('[data-cloud-url]').forEach(b=>b.onclick=async()=>{b.disabled=true;b.textContent='Uploading…';try{const x=await api('/api/storage/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({output_url:b.dataset.cloudUrl})});await navigator.clipboard?.writeText(assetUrl(x.url));b.textContent='Cloud URL copied ✓';}catch(e){alert(e.message);b.textContent='Cloud';b.disabled=false}});}


function comparePage(){
  const voices=state.voices.filter(v=>(v.capabilities||[]).includes('tts'));
  const opts=voices.map(v=>`<option value="${esc(v.id)}">${esc(v.name)} · ${esc(v.provider)}</option>`).join('');
  return layout(`<div class="tool-page">${hero('A/B Voice Compare','Generate the same script with two voices and compare them side by side.','Voice audition')}<div class="panel"><textarea id="compareText" maxlength="4096">This is an A/B comparison of two AI voices using the exact same script.</textarea><div class="compare-grid"><div><label>Voice A<select id="voiceA">${opts}</select></label><div id="compareA" class="compare-output"></div></div><div><label>Voice B<select id="voiceB">${opts}</select></label><div id="compareB" class="compare-output"></div></div></div><button class="btn primary wide" id="compareGo">Generate both</button></div></div>`)
}
function bindCompare(){bindNav();const a=$('#voiceA'),b=$('#voiceB');if(b&&b.options.length>1)b.selectedIndex=1;$('#compareGo').onclick=async()=>{const btn=$('#compareGo'),text=$('#compareText').value;btn.disabled=true;btn.textContent='Queued…';const payload=id=>({text,voice_id:id,volume_db:0,speed:1,emotion:'neutral',emotion_intensity:50});try{const [ja,jb]=await Promise.all([api('/api/jobs/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload(a.value))}),api('/api/jobs/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload(b.value))})]);state.jobs.unshift(ja,jb);pollJob(ja.id,$('#compareA'));pollJob(jb.id,$('#compareB'));}catch(e){$('#compareA').innerHTML=errorBox(e.message)}finally{btn.disabled=false;btn.textContent='Generate both'}}}

async function editorPage(){
  const items=await api('/api/history?limit=50').catch(()=>[]);const urls=items.filter(i=>i.output_path).map(i=>({title:i.title,url:`/api/files/${encodeURIComponent(fileNameFromPath(i.output_path))}`}));
  if(!state.editorUrl&&urls.length)state.editorUrl=urls[0].url;
  return layout(`<div class="tool-page">${hero('Audio Editor','Trim a generated clip, adjust gain, and add fades without leaving VoiceLab.','Non-destructive export')}<div class="panel"><label>Source clip<select id="editorSource">${urls.map(x=>`<option value="${x.url}" ${x.url===state.editorUrl?'selected':''}>${esc(x.title)}</option>`).join('')}</select></label>${state.editorUrl?`<div class="editor-preview"><canvas data-wave-url="${assetUrl(state.editorUrl)}" class="waveform" width="900" height="110"></canvas><audio id="editorAudio" controls src="${assetUrl(state.editorUrl)}"></audio></div>`:notice('Generate some audio first, then return here to edit it.')}<div class="settings-grid"><label>Trim start (seconds)<input id="trimStart" type="number" min="0" step="0.1" value="0"></label><label>Trim end (seconds)<input id="trimEnd" type="number" min="0.1" step="0.1" placeholder="full clip"></label><label>Gain (dB)<input id="editGain" type="range" min="-24" max="24" step="1" value="0"><b id="editGainLabel">0 dB</b></label><label>Fade in (s)<input id="fadeIn" type="number" min="0" max="30" step="0.1" value="0"></label><label>Fade out (s)<input id="fadeOut" type="number" min="0" max="30" step="0.1" value="0"></label></div><button class="btn primary wide" id="editGo" ${state.editorUrl?'':'disabled'}>Export edit</button><div id="editorResult"></div></div></div>`)
}
function bindEditor(){bindNav();hydrateWaveforms();const src=$('#editorSource');if(src)src.onchange=()=>{state.editorUrl=src.value;render();};const audio=$('#editorAudio');if(audio)audio.onloadedmetadata=()=>{$('#trimEnd').placeholder=audio.duration.toFixed(2);};$('#editGain')?.addEventListener('input',e=>$('#editGainLabel').textContent=`${e.target.value} dB`);$('#editGo')?.addEventListener('click',async()=>{const btn=$('#editGo');btn.disabled=true;btn.textContent='Exporting…';try{const end=$('#trimEnd').value;const x=await api('/api/audio/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({output_url:state.editorUrl,start_seconds:+$('#trimStart').value||0,end_seconds:end?+end:null,gain_db:+$('#editGain').value,fade_in:+$('#fadeIn').value||0,fade_out:+$('#fadeOut').value||0})});$('#editorResult').innerHTML=audioResult(x.audio_url,'Edited VoiceLab audio');hydrateWaveforms($('#editorResult'));}catch(e){$('#editorResult').innerHTML=errorBox(e.message)}finally{btn.disabled=false;btn.textContent='Export edit'}})}

function accountPage(){
  if(!state.user)return layout(`<div class="tool-page">${hero('Account','Create a local VoiceLab profile or sign in. The first account created becomes the workspace administrator.','Local account')}<div class="auth-grid"><div class="panel form"><h3>Create account</h3><label>Display name<input id="regName"></label><label>Email<input id="regEmail" type="email"></label><label>Password<input id="regPass" type="password" minlength="8"></label><button class="btn primary" id="registerBtn">Create account</button><div id="registerMsg"></div></div><div class="panel form"><h3>Sign in</h3><label>Email<input id="loginEmail" type="email"></label><label>Password<input id="loginPass" type="password"></label><button class="btn secondary" id="loginBtn">Sign in</button><div id="loginMsg"></div></div></div></div>`);
  return layout(`<div class="tool-page">${hero('Account',`Signed in as ${state.user.email}`,state.user.is_admin?'Administrator':'Member')}<div class="panel form profile-panel"><label>Display name<input id="profileName" value="${esc(state.user.display_name)}"></label><button class="btn primary" id="saveProfile">Save profile</button><button class="btn ghost" id="logoutBtn">Sign out</button><div id="profileMsg"></div></div></div>`)
}
function bindAccount(){bindNav();if(!state.user){$('#registerBtn').onclick=async()=>{try{const x=await api('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:$('#regName').value,email:$('#regEmail').value,password:$('#regPass').value})});state.token=x.token;state.user=x.user;localStorage.setItem('voicelab_token',state.token);render()}catch(e){$('#registerMsg').innerHTML=errorBox(e.message)}};$('#loginBtn').onclick=async()=>{try{const x=await api('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('#loginEmail').value,password:$('#loginPass').value})});state.token=x.token;state.user=x.user;localStorage.setItem('voicelab_token',state.token);render()}catch(e){$('#loginMsg').innerHTML=errorBox(e.message)}};return;}$('#saveProfile').onclick=async()=>{try{state.user=await api('/api/auth/profile',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:$('#profileName').value})});$('#profileMsg').innerHTML=notice('Profile saved.')}catch(e){$('#profileMsg').innerHTML=errorBox(e.message)}};$('#logoutBtn').onclick=async()=>{await api('/api/auth/logout',{method:'POST'}).catch(()=>{});state.token='';state.user=null;localStorage.removeItem('voicelab_token');render()}}

async function adminPage(){
  if(!state.user?.is_admin)return layout(`<div class="tool-page">${hero('Admin','Workspace administration')} ${notice('Sign in with the administrator account to use this page.')}</div>`);
  const [sum,cat]=await Promise.all([api('/api/admin/summary'),api('/api/admin/catalog')]);
  return layout(`<div class="tool-page">${hero('Admin','Manage the local VoiceLab catalog, storage, providers, and workspace health.','Workspace control')}<div class="stats-row admin-stats"><div><b>${sum.users}</b><span>Users</span></div><div><b>${sum.jobs}</b><span>Jobs</span></div><div><b>${sum.history}</b><span>Outputs</span></div><div><b>${sum.shares}</b><span>Shares</span></div></div><div class="panel"><h3>Catalog moderation</h3><div class="admin-catalog">${cat.map(x=>`<div class="admin-row"><div><b>${esc(x.name)}</b><small>${esc(x.provider)} · ${esc(x.kind)}</small></div><label class="switchline"><input type="checkbox" data-admin-catalog="${esc(x.id)}" ${x.enabled?'checked':''}> Enabled</label></div>`).join('')}</div></div><div class="panel storage-panel"><h3>Cloud storage</h3><p class="muted">Use local storage or mirror finished clips to any S3-compatible service.</p><div class="settings-grid"><label>Backend<select id="storageBackend"><option value="local" ${sum.storage.backend==='local'?'selected':''}>Local</option><option value="s3" ${sum.storage.backend==='s3'?'selected':''}>S3-compatible</option></select></label><label>Bucket<input id="s3Bucket" value="${esc(sum.storage.bucket||'')}"></label><label>Region<input id="s3Region" value="${esc(sum.storage.region||'')}"></label><label>Endpoint URL<input id="s3Endpoint" value="${esc(sum.storage.endpoint||'')}"></label><label>Access key<input id="s3Access" type="password"></label><label>Secret key<input id="s3Secret" type="password"></label><label>Public base URL (optional)<input id="s3Public"></label></div><button class="btn primary" id="saveStorage">Save storage</button><div id="storageMsg"></div></div></div>`)
}
function bindAdmin(){bindNav();$$('[data-admin-catalog]').forEach(c=>c.onchange=async()=>{try{await api('/api/admin/catalog/'+encodeURIComponent(c.dataset.adminCatalog),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:c.checked,note:''})});state.catalog=[];}catch(e){alert(e.message);c.checked=!c.checked}});$('#saveStorage')?.addEventListener('click',async()=>{try{const x=await api('/api/storage/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({backend:$('#storageBackend').value,bucket:$('#s3Bucket').value,region:$('#s3Region').value,endpoint_url:$('#s3Endpoint').value,access_key_id:$('#s3Access').value,secret_access_key:$('#s3Secret').value,public_base_url:$('#s3Public').value})});$('#storageMsg').innerHTML=notice(`Storage set to ${esc(x.backend)}${x.bucket?' · '+esc(x.bucket):''}.`)}catch(e){$('#storageMsg').innerHTML=errorBox(e.message)}})}

async function loadUser(){if(!state.token)return;try{state.user=await api('/api/auth/me')}catch{state.token='';state.user=null;localStorage.removeItem('voicelab_token')}}

const providerInfo={
  openai:{name:'OpenAI',desc:'Studio text-to-speech voices.',cap:'TTS'},elevenlabs:{name:'ElevenLabs',desc:'TTS, shared voice library, sound effects, voice conversion.',cap:'TTS · SFX · Conversion'},respeecher:{name:'Respeecher',desc:'Licensed professional speech voices.',cap:'TTS'},speechify:{name:'Speechify',desc:'Shared speech voice catalog.',cap:'TTS'},kits:{name:'Kits AI',desc:'Voice conversion and singing workflows.',cap:'Conversion'},voice_swap:{name:'Voice-Swap',desc:'Rights-managed voice platform; catalog integration slot.',cap:'Provider integration'},veritone:{name:'Veritone Voice',desc:'Stock and premium licensed voice platform.',cap:'Provider integration'}
};
async function settingsPage(){
  const status=await api('/api/providers/status').catch(()=>({}));
  return layout(`<div class="tool-page">${hero('Provider Setup','Connect voice providers without editing configuration files manually. API keys are written to the local backend only.','One-click local setup')}<div class="panel"><div class="provider-grid">${Object.entries(providerInfo).map(([id,p])=>`<div class="provider-card"><div class="provider-title"><div><b>${p.name}</b><small>${p.cap}</small></div><span class="status-dot ${status[id]?.configured?'ok':''}">${status[id]?.configured?'Connected':'Not connected'}</span></div><p>${p.desc}</p><div class="key-row"><input type="password" id="key-${id}" placeholder="Paste API key"><button class="btn primary compact" data-save-provider="${id}">${status[id]?.configured?'Replace':'Connect'}</button>${status[id]?.configured?`<button class="btn ghost compact" data-remove-provider="${id}">Disconnect</button>`:''}</div></div>`).join('')}</div></div><div class="panel diagnostics"><h3>Diagnostics</h3><button class="btn secondary" id="health">Run diagnostics</button><div id="toolMessage"></div>${notice('Keys are stored in <code>apps/api/.env</code> on your machine. They are never returned by the API or embedded in the browser bundle.')}</div></div>`)
}
function bindSettings(){
  bindNav();$$('[data-save-provider]').forEach(b=>b.onclick=async()=>{const id=b.dataset.saveProvider,key=$('#key-'+id).value.trim();if(!key)return;const old=b.textContent;b.disabled=true;b.textContent='Saving…';try{await api('/api/providers/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:id,api_key:key})});await render();}catch(e){alert(e.message);b.disabled=false;b.textContent=old}});
  $$('[data-remove-provider]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/providers/'+b.dataset.removeProvider,{method:'DELETE'});await render();}catch(e){alert(e.message);b.disabled=false}});
  $('#health').onclick=async()=>{const m=$('#toolMessage');try{const x=await api('/api/health');m.innerHTML=notice(`API: OK · FFmpeg: ${x.ffmpeg?'found':'missing'} · Demucs: ${x.demucs?'found':'missing'} · Connected: ${Object.entries(x.providers||{}).filter(([,v])=>v).map(([k])=>k).join(', ')||'none'}`)}catch(e){m.innerHTML=errorBox(e.message)}};
}

async function loadVoices(){state.voices=await api('/api/voices').catch(()=>[])}
async function loadJobs(){state.jobs=await api('/api/jobs?limit=25').catch(()=>[])}
async function render(){
  let html,binder=bindNav;
  if(state.page==='voice'){html=ttsPage('studio','AI Voice Generator');binder=()=>bindTTS('studio')}
  else if(state.page==='character'){html=ttsPage('character','Character Voice Generator');binder=()=>bindTTS('character')}
  else if(state.page==='licensed'){html=ttsPage('licensed','Licensed Voice Generator');binder=()=>bindTTS('licensed')}
  else if(state.page==='marketplace'){html=await marketplacePage();binder=bindMarketplace}
  else if(state.page==='cover'){html=coverPage();binder=bindCover}
  else if(state.page==='sfx'){html=sfxPage();binder=bindSfx}
  else if(state.page==='isolate'){html=fileTool('isolate','Vocal Isolator','Extract a clean vocal stem from music, audio, or video.','Isolate vocals');binder=()=>bindFileTool('isolate','Isolate vocals')}
  else if(state.page==='remove'){html=fileTool('remove','Vocal Remover','Remove vocals and create an instrumental/karaoke track.','Remove vocals');binder=()=>bindFileTool('remove-vocals','Remove vocals')}
  else if(state.page==='extract'){html=fileTool('extract','Audio Extractor','Extract high-quality audio from a video file.','Extract audio');binder=()=>bindFileTool('extract','Extract audio')}
  else if(state.page==='library'){html=libraryPage();binder=bindLibrary}
  else if(state.page==='compare'){html=comparePage();binder=bindCompare}
  else if(state.page==='editor'){html=await editorPage();binder=bindEditor}
  else if(state.page==='queue'){html=await queuePage();binder=bindQueue}
  else if(state.page==='history'){html=await historyPage();binder=bindHistory}
  else if(state.page==='account'){html=accountPage();binder=bindAccount}
  else if(state.page==='admin'){html=await adminPage();binder=bindAdmin}
  else {html=await settingsPage();binder=bindSettings}
  $('#app').innerHTML=html;binder();hydrateWaveforms();
}

await Promise.all([loadVoices(),loadFavorites(),loadJobs(),loadUser()]);await render();
