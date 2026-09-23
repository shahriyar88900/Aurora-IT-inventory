const state={assets:[],employees:[],users:[],network:[],me:null,view:'overview',search:'',employeeSearch:'',status:'All status',category:'All categories',departments:[],designationsByDepartment:{}};
const NETWORK_LOCATIONS=['CCB','DM Plant','Dormitory','Workshop','UEB'];
const ROUTER_BRANDS=['TP-LINK TL-XVR3000G','TP-LINK TL-XDR3030','TL-Archer C20','TL-WR841N','TL-WR840N','TP-Deco M5','TL-MR6400','TP-Link C54'];
const SWITCH_BRANDS=['Fast','TP-Link'];
const brandsFor=t=>t==='Router'?ROUTER_BRANDS:t==='Switch'?SWITCH_BRANDS:[];
const CCB_FLOORS=['Ground Floor','1st Floor','2nd Floor','3rd Floor'];
const DORM_FLOORS=['Ground Floor','1st Floor','2nd Floor','3rd Floor','4th Floor'];
const floorsFor=loc=>loc==='CCB'?CCB_FLOORS:loc==='Dormitory'?DORM_FLOORS:[];
const RAM_OPTIONS=['4GB','8GB','16GB','32GB','64GB'];
const ASSET_LOCATIONS=['CCB','DM Plant','UEB','Warehouse','Workshop'];
const STORAGE_OPTIONS=['128 GB','256 GB','512 GB','1 TB','2 TB'];
const IP_LESS_CATEGORIES=['Monitor','Mouse','Keyboard','Printer'];
const ASSET_BRANDS=['Asus','Golden Field','HP','Dell','Lenovo','Qbit','Chuwi'];
const INTEL_PROCESSORS=['Core i3','Core i5','Core i7','Core i9','Core Ultra 5','Core Ultra 7','Core Ultra 9'];
const AMD_PROCESSORS=['Ryzen 3','Ryzen 5','Ryzen 7','Ryzen 9','Threadripper','EPYC','Athlon','FX','A-Series'];
const INTEL_GENERATIONS=['8th Gen','9th Gen','10th Gen','11th Gen','12th Gen','13th Gen','14th Gen'];
const AMD_GENERATIONS=['5th Gen','6th Gen','7th Gen','8th Gen','9th Gen'];
const processorsFor=m=>m==='Intel'?INTEL_PROCESSORS:m==='AMD'?AMD_PROCESSORS:[];
const generationsFor=m=>m==='Intel'?INTEL_GENERATIONS:m==='AMD'?AMD_GENERATIONS:[];
// Populate a <select>; if the stored value isn't in the option list (e.g. legacy
// data) it is injected first so existing records are never silently changed.
function fillSelect(select,options,selected='',placeholder=''){
  const opts=[...options];
  if(selected&&!opts.includes(selected))opts.unshift(selected);
  select.innerHTML=(placeholder?`<option value="">${placeholder}</option>`:'')+opts.map(o=>`<option${o===selected?' selected':''}>${esc(o)}</option>`).join('');
}
const $=s=>document.querySelector(s);
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const money=value=>new Intl.NumberFormat('en-BD',{style:'currency',currency:'BDT',maximumFractionDigits:0}).format(Number(value)||0);
const date=value=>value?new Date(`${value}T00:00:00`).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'}):'Not recorded';
const statusClass=s=>['Active','In use'].includes(s)?'active-status':s==='In stock'?'stock-status':s==='Damaged'?'damaged-status':s==='In warranty'?'warranty-status':s==='Repair'?'repair-status':'retired-status';
const status=s=>`<span class="status ${statusClass(s)}">${esc(s)}</span>`;
const initials=s=>(s||'IT').split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase();
const identity=a=>`<div class="asset"><span class="asset-icon">${esc(initials(a.category))}</span><div><strong>${esc(a.name)}</strong><small>${esc(a.asset_tag)}</small></div></div>`;

async function api(url,options={}){
  const r=await fetch(url,options);
  let data={};try{data=await r.json()}catch{}
  if(r.status===401){showLogin();throw new Error(data.error||'Please sign in again')}
  if(!r.ok)throw new Error(data.error||'Request failed');
  return data;
}

async function start(){
  bindGlobal();
  try{const data=await api('/api/auth/me');await enterApp(data.user)}catch{showLogin()}
}

function showLogin(){
  state.me=null;state.assets=[];state.employees=[];state.users=[];
  $('#app').classList.add('hidden');$('#loginScreen').classList.remove('hidden');
}

async function enterApp(user){
  state.me=user;
  $('#loginScreen').classList.add('hidden');$('#app').classList.remove('hidden');
  $('#profileName').textContent=user.full_name;$('#profileInitials').textContent=initials(user.full_name);
  $('#profileRole').textContent=`${user.designation||'Not specified'} • ${user.is_main_admin?'Main Admin':user.role==='admin'?'Administrator':'User'}`;
  const roleLabel=user.is_main_admin?'Main Admin':user.role==='admin'?'Administrator':'User';
  const tpn=$('#topProfileName');if(tpn)tpn.textContent=user.full_name;
  const tpi=$('#topProfileInitials');if(tpi)tpi.textContent=initials(user.full_name);
  const tpr=$('#topProfileRole');if(tpr)tpr.textContent=roleLabel;
  const rights=user.is_main_admin?'Full access':user.role==='user'?'My assigned assets only':[user.can_read&&'Read',user.can_write&&'Add/Edit',user.can_delete&&'Delete'].filter(Boolean).join(' • ')||'No inventory access';
  $('#permissionChip').textContent=rights;
  document.querySelectorAll('.write-only').forEach(el=>el.classList.toggle('hidden',!user.can_write));
  document.querySelectorAll('.read-only').forEach(el=>el.classList.toggle('hidden',!user.can_read));
  document.querySelectorAll('.administrator-only').forEach(el=>el.classList.toggle('hidden',user.role!=='admin'));
  document.querySelectorAll('.main-admin-only').forEach(el=>el.classList.toggle('hidden',!user.is_main_admin));
  document.querySelectorAll('.export-only').forEach(el=>el.classList.toggle('hidden',user.role!=='admin'||!user.can_read));
  $('#assetsNavLabel').textContent=user.role==='user'?'My Assets':'Assets';
  state.view=user.role==='user'?'assets':user.can_read?'overview':'settings';
  if(user.can_read){await loadAssets(false);if(user.role==='admin'){await loadEmployees(false);await loadNetwork(false)}updateBadges();render()}else{render()}
  if(user.must_change_password){openForcePasswordModal()}
}

async function login(event){
  event.preventDefault();const form=event.currentTarget,error=$('#loginError'),button=form.querySelector('.login-button');
  error.classList.add('hidden');button.disabled=true;button.textContent='Signing in…';
  try{const data=await api('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});form.reset();await enterApp(data.user)}
  catch(e){error.textContent=e.message;error.classList.remove('hidden')}
  finally{button.disabled=false;button.textContent='Sign in securely →'}
}

async function logout(){try{await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}finally{showLogin()}}

async function loadAssets(shouldRender=true){
  try{const data=await api('/api/assets');state.assets=data.assets||[];updateBadges();if(shouldRender)render()}
  catch(e){showNotice(e.message)}
}

async function loadEmployees(shouldRender=true){
  try{const data=await api('/api/employees');state.employees=data.employees||[];state.departments=data.departments||[];state.designationsByDepartment=data.designations_by_department||{};updateBadges();if(shouldRender)render()}
  catch(e){showNotice(e.message)}
}

async function loadNetwork(shouldRender=true){
  try{const data=await api('/api/network-devices');state.network=data.devices||[];updateBadges();if(shouldRender)render()}
  catch(e){showNotice(e.message)}
}

let noticeTimer=null;
function showNotice(message,ok=false){const box=$('#notice');if(noticeTimer)clearTimeout(noticeTimer);box.textContent=message;box.classList.remove('hidden');box.classList.toggle('success',ok);const modalOpen=!!document.querySelector('.modal-wrap:not(.hidden)');box.classList.toggle('notice-float',modalOpen);if(!modalOpen)box.scrollIntoView({block:'nearest'});noticeTimer=setTimeout(()=>box.classList.add('hidden'),ok?4200:9000)}
function updateBadges(){const alerts=state.assets.filter(a=>['Repair','Damaged','In warranty'].includes(a.status)).length;$('#assetCount').textContent=state.assets.length;$('#employeeCount').textContent=state.employees.length;$('#alertCount').textContent=alerts;const nc=$('#networkCount');if(nc)nc.textContent=state.network.length}
function filtered(){const q=state.search.toLowerCase();return state.assets.filter(a=>(!q||[a.asset_tag,a.name,a.serial,a.assigned_to,a.location,a.ip_address].some(v=>(v||'').toLowerCase().includes(q)))&&(state.status==='All status'||a.status===state.status)&&(state.category==='All categories'||a.category===state.category))}
function departments(){const map={};state.assets.forEach(a=>map[a.department||'Unassigned']=(map[a.department||'Unassigned']||0)+1);return Object.entries(map).sort((a,b)=>b[1]-a[1])}
function heading(){const assetsHeading=state.me?.role==='user'?['My Assets','Devices currently assigned to you and their distribution dates.']:['Assets','Search, assign and manage the complete asset lifecycle.'];const copy={overview:['Overview','A live view of every technology asset across the plant.'],assets:assetsHeading,employees:['Employees','Add, delete, assign devices and receive returned equipment.'],maintenance:['Maintenance','Damaged, warranty and repair items that need attention.'],reports:['Reports','Understand inventory distribution and record quality.'],network:['Network Devices','Manage plant routers and switches across all locations.'],access:['Access Management','Create login accounts directly from the employee list.'],settings:['Settings','Manage your account and application preferences.']}[state.view]||['Overview','Aurora Plant IT Inventory'];$('#pageTitle').textContent=copy[0];$('#pageSubtitle').textContent=copy[1]}
function render(){if(state.me.role==='user'&&!['assets','settings'].includes(state.view))state.view='assets';if(state.view==='access'&&!state.me.is_main_admin)state.view='settings';heading();document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));const view=$('#view');view.innerHTML=!state.me.can_read&&!['settings','access'].includes(state.view)?noAccess():state.view==='overview'?overview():state.view==='assets'?assetsView():state.view==='employees'?employeesView():state.view==='maintenance'?maintenance():state.view==='reports'?reports():state.view==='network'?networkView():state.view==='access'?accessControl():settings();bindView()}

function noAccess(){return `<section class="panel no-access"><span>🔒</span><h2>Inventory access is not enabled</h2><p>Ask an administrator to grant Read permission to this account.</p></section>`}

function overview(){
  const all=state.assets.length,active=state.assets.filter(a=>['Active','In use'].includes(a.status)).length,stock=state.assets.filter(a=>a.status==='In stock').length,attention=state.assets.filter(a=>['Repair','Damaged','In warranty'].includes(a.status)).length,dept=departments(),max=Math.max(...dept.map(x=>x[1]),1),healthy=all?Math.round((active+stock)/all*100):0;
  const metrics=[['Total assets',all,'Across all locations','▦',''],['In use',active,`${all?Math.round(active/all*100):0}% utilization rate`,'✓','green'],['Available stock',stock,'Ready for distribution','□','blue'],['Need attention',attention,'Currently under repair','!','orange']];
  return `<section class="metrics">${metrics.map(m=>`<article class="metric ${m[4]}"><div class="label"><span>${m[0]}</span><b>•••</b></div><strong>${String(m[1]).padStart(2,'0')}</strong><footer><i>${m[3]}</i><small>${m[2]}</small></footer></article>`).join('')}</section>
  <section class="grid"><article class="panel"><header class="panel-head"><div><h2>Asset allocation</h2><p>Distribution by department</p></div><button data-go="reports">View report</button></header><div class="bars">${dept.slice(0,6).map(([n,c])=>`<div class="bar"><span>${esc(n)}</span><div><i style="width:${c/max*100}%"></i></div><strong>${c}</strong></div>`).join('')}</div></article>
  <article class="panel"><header class="panel-head"><div><h2>Inventory health</h2><p>Lifecycle status overview</p></div><b>◉</b></header><div class="donut" style="background:conic-gradient(var(--purple) 0 ${all?active/all*100:0}%,#2cb985 0 ${all?(active+stock)/all*100:0}%,#e99a36 0 100%)"><div><strong>${healthy}%</strong><small>Healthy</small></div></div><div class="legend"><span><i></i>In use<b>${active}</b></span><span><i></i>In stock<b>${stock}</b></span><span><i></i>Repair<b>${attention}</b></span></div></article></section>
  <section class="panel"><header class="panel-head"><div><h2>Recent assets</h2><p>Latest inventory records and updates</p></div><button data-go="assets">View all assets</button></header><div class="table-scroll"><table><thead><tr><th>Asset</th><th>Category</th><th>User / Department</th><th>Arrival</th><th>Device add date</th><th>Status</th><th></th></tr></thead><tbody>${state.assets.slice(0,5).map(a=>`<tr><td>${identity(a)}</td><td>${esc(a.category)}</td><td>${assignmentIdentity(a)}</td><td>${date(a.arrival_date)}</td><td>${date(a.distribution_date)}</td><td>${status(a.status)}</td><td>${state.me.can_write?`<div class="actions"><button data-edit="${a.id}">✎</button></div>`:''}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function assignmentIdentity(a){return a.assigned_to&&a.assigned_to!=='Unassigned'?`<div class="assigned-person"><strong>${esc(a.assigned_to)}</strong><small>${esc(a.department||'No department')}</small></div>`:'<span class="muted">Unassigned</span>'}

function specifications(a){const proc=[a.processor_mfr,a.processor,a.cpu_generation,a.cpu_series].filter(Boolean).join(' ')||a.cpu;const values=[a.ram&&`RAM: ${a.ram}`,proc&&`Processor: ${proc}`,a.ssd&&`SSD: ${a.ssd}`,a.hdd&&`HDD: ${a.hdd}`].filter(Boolean);return values.length?`<div class="spec-line">${values.map(v=>`<span>${esc(v)}</span>`).join('')}</div>`:'<span class="muted">No computer specifications</span>'}

function assetsView(){const rows=filtered(),cats=[...new Set(state.assets.map(a=>a.category))].sort();if(state.me.role==='user')return `<section class="my-assets-intro"><h2>${rows.length?`${rows.length} device${rows.length===1?' is':'s are'} assigned to you`:'No device is currently assigned to you'}</h2><p>This page only shows assets linked to your Employee ID. Contact the Main Admin if a record is incorrect.</p></section><section class="panel"><div class="table-scroll"><table><thead><tr><th>Asset</th><th>Category / Specifications</th><th>Serial</th><th>Distribution date</th><th>Status</th></tr></thead><tbody>${rows.map(a=>`<tr><td>${identity(a)}</td><td><b>${esc(a.category)}</b>${['Laptop','Desktop'].includes(a.category)?specifications(a):''}</td><td>${esc(a.serial||'—')}</td><td><strong>${date(a.distribution_date)}</strong></td><td>${status(a.status)}</td></tr>`).join('')}</tbody></table>${rows.length?'':'<div class="empty"><b>No assigned assets</b><p>Your assigned devices will appear here automatically.</p></div>'}</div></section>`;return `<section class="panel"><div class="filterbar"><select id="statusFilter"><option>All status</option>${['In use','In stock','Damaged','In warranty','Repair','Retired'].map(x=>`<option ${state.status===x?'selected':''}>${x}</option>`).join('')}</select><select id="categoryFilter"><option>All categories</option>${cats.map(x=>`<option ${state.category===x?'selected':''}>${esc(x)}</option>`).join('')}</select><span>${rows.length} records</span>${state.me.can_write?'<button class="primary" data-add-asset>＋ Add asset</button>':''}${state.me.can_write?'<button class="secondary" data-import-asset>⬆ Import Excel</button>':''}</div><div class="table-scroll"><table><thead><tr><th>Asset</th><th>Serial / IP</th><th>User / Department</th><th>Location</th><th>Arrival / Distribution</th><th>Status</th><th></th></tr></thead><tbody>${rows.map(a=>`<tr><td>${identity(a)}${['Laptop','Desktop'].includes(a.category)?specifications(a):''}</td><td><b>${esc(a.serial||'—')}</b><small>${esc(a.ip_address||'No IP')}</small></td><td>${assignmentIdentity(a)}</td><td>${esc(a.location)}</td><td><b>${date(a.arrival_date)}</b><small>${a.status==='In use'?date(a.distribution_date):'Not assigned'}</small></td><td>${status(a.status)}</td><td><div class="actions">${state.me.can_write?`<button title="Edit" data-edit="${a.id}">✎</button>`:''}${state.me.can_delete?`<button class="delete" title="Delete" data-delete="${a.id}">×</button>`:''}</div></td></tr>`).join('')}</tbody></table>${rows.length?'':'<div class="empty"><b>No matching assets</b><p>Try changing the search or filters.</p></div>'}</div></section>`}

function contactInfo(e){
  if(!e.phone&&!e.email)return '<span class="muted">—</span>';
  return `${e.phone?`<div>${esc(e.phone)}</div>`:''}${e.email?`<small>${esc(e.email)}</small>`:''}`;
}
function employeesView(){
  const gq=state.employeeSearch.trim().toLowerCase();
  const match=e=>!gq||(e.name||'').toLowerCase().includes(gq)||(e.employee_id||'').toLowerCase().includes(gq);
  const active=state.employees.filter(e=>e.active).filter(match);
  const resigned=state.employees.filter(e=>!e.active).filter(match);
  const resignedSection=resigned.length?`
  <section class="panel"><header class="panel-head"><div><h2>Resigned employees</h2><p>Historical record of departed staff and the assets they previously held.</p></div><span class="permission-summary">${resigned.length} record${resigned.length===1?'':'s'}</span></header>
  <div class="table-scroll"><table><thead><tr><th>Employee</th><th>Department</th><th>Designation</th><th>Contact</th><th>Previously assigned assets</th><th>Resignation date</th>${state.me.can_delete?'<th></th>':''}</tr></thead><tbody>${resigned.map(e=>`<tr><td><div class="asset"><span class="avatar">${initials(e.name)}</span><div><strong>${esc(e.name)}</strong><small>${esc(e.employee_id)}</small></div></div></td><td><span class="department-badge">${esc(e.department)}</span></td><td>${esc(e.designation)}</td><td>${contactInfo(e)}</td><td><div class="device-list">${(e.history&&e.history.length)?e.history.map(d=>`<div class="device-chip"><span><b>${esc(d.asset_name)}</b><small>${esc(d.asset_tag)} • ${date(d.assigned_date)}${d.returned_date?` → ${date(d.returned_date)}`:''}</small></span></div>`).join(''):'<span class="muted">No assets were assigned</span>'}</div></td><td><strong>${date(e.resignation_date)}</strong></td>${state.me.can_delete?`<td><div class="actions"><button class="delete delete-employee" data-employee-delete="${e.id}" title="Delete permanently">×</button></div></td>`:''}</tr>`).join('')}</tbody></table></div></section>`:'';
  return `<section class="employee-summary"><article><span>Active employees</span><strong>${state.employees.filter(e=>e.active).length}</strong></article><article><span>Resigned employees</span><strong>${state.employees.filter(e=>!e.active).length}</strong></article><article><span>Assigned devices</span><strong>${state.employees.reduce((n,e)=>n+e.devices.length,0)}</strong></article><article><span>Available devices</span><strong>${state.assets.filter(a=>a.status==='In stock').length}</strong></article></section>
  <section class="panel"><header class="panel-head"><div><h2>Employee &amp; device directory</h2><p>Name, ID, designation, department and current equipment. Employees are grouped department by department.</p></div><div class="head-actions">${state.me.can_write?'<button class="secondary" data-import-employee>⬆ Import Excel</button>':''}${state.me.can_write?'<button class="primary" data-add-employee>＋ Add employee</button>':''}</div></header>
  <div class="filterbar"><label class="search inline"><span>⌕</span><input id="employeeSearch" value="${esc(state.employeeSearch)}" placeholder="Search employee by name or ID..."></label><span>${active.length} record${active.length===1?'':'s'}</span></div>
  <div class="table-scroll"><table><thead><tr><th>Employee</th><th>ID</th><th>Designation</th><th>Department</th><th>Contact</th><th>Assigned devices</th><th>Status</th><th></th></tr></thead><tbody>${active.map(e=>`<tr><td><div class="asset"><span class="avatar">${initials(e.name)}</span><div><strong>${esc(e.name)}</strong><small>${e.devices.length} device${e.devices.length===1?'':'s'}</small></div></div></td><td><strong>${esc(e.employee_id)}</strong></td><td>${esc(e.designation)}</td><td><span class="department-badge">${esc(e.department)}</span></td><td>${contactInfo(e)}</td><td><div class="device-list">${e.devices.length?e.devices.map(d=>`<div class="device-chip"><span><b>${esc(d.asset_name)}</b><small>${esc(d.asset_tag)} • Added ${date(d.assigned_date)}</small></span>${state.me.can_write?`<button data-return="${d.assignment_id}" data-device="${esc(d.asset_tag)}" data-person="${esc(e.name)}">↩ Return</button>`:''}</div>`).join(''):'<span class="muted">No device assigned</span>'}</div></td><td><span class="status active-status">Active</span></td><td><div class="employee-actions">${state.me.can_write?`<button class="secondary" data-assign="${e.id}">＋ Device</button><button data-employee-edit="${e.id}" title="Edit employee">✎</button><button class="resign-btn" data-resign="${e.id}" title="Mark as resigned">⏻ Resign</button>`:''}${state.me.can_delete?`<button class="delete delete-employee" data-employee-delete="${e.id}" title="Delete employee permanently">×</button>`:''}</div></td></tr>`).join('')}</tbody></table>${active.length?'':'<div class="empty"><b>No matching active employees</b><p>Try a different name or ID, or add a new employee.</p></div>'}</div></section>
  ${resignedSection}`;
}

function populateDesignationOptions(selectedDesignation=''){
  const department=$('#employeeDepartment').value;
  const options=state.designationsByDepartment[department]||[];
  fillSelect($('#employeeDesignation'),options,selectedDesignation,department?'Select designation':'Select department first');
}
function openEmployeeModal(id){
  if(!state.me.can_write)return showNotice('Write permission is required');
  const form=$('#employeeForm');form.reset();form.elements.id.value='';
  fillSelect($('#employeeDepartment'),state.departments,'','Select department');
  if(id){
    const e=state.employees.find(x=>x.id===id);
    form.elements.id.value=e.id;form.elements.name.value=e.name;form.elements.employee_id.value=e.employee_id;
    form.elements.department.value=e.department;populateDesignationOptions(e.designation);
    form.elements.phone.value=e.phone||'';form.elements.email.value=e.email||'';
    $('#employeeModalTitle').textContent=`Edit ${e.name}`;
  }else{
    populateDesignationOptions();
    $('#employeeModalTitle').textContent='Add employee';
  }
  $('#employeeModalWrap').classList.remove('hidden');form.elements.name.focus();
}
function closeEmployeeModal(){$('#employeeModalWrap').classList.add('hidden')}
async function saveEmployee(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form)),id=data.id;delete data.id;const button=$('#saveEmployee');button.disabled=true;try{await api(id?`/api/employees/${id}`:'/api/employees',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});closeEmployeeModal();await Promise.all([loadAssets(false),loadEmployees(false)]);updateBadges();render();showNotice(id?'Employee updated successfully':'Employee added successfully',true)}catch(e){showNotice(e.message)}finally{button.disabled=false}}

function openAssignmentModal(employeeId){
  const employee=state.employees.find(e=>e.id===employeeId),available=state.assets.filter(a=>a.status==='In stock');
  if(!available.length)return showNotice('No In stock device is available');
  const form=$('#assignmentForm');form.reset();form.elements.employee_id.value=employee.id;form.elements.asset_id.innerHTML='<option value="">Select a device</option>'+available.map(a=>`<option value="${a.id}">${esc(a.category)} — ${esc(a.brand)} ${esc(a.model||a.name)} (${esc(a.asset_tag)})</option>`).join('');
  $('#assignmentPerson').innerHTML=`<span class="avatar">${initials(employee.name)}</span><div><strong>${esc(employee.name)}</strong><small>${esc(employee.employee_id)} • ${esc(employee.designation)} • ${esc(employee.department)}</small></div>`;
  $('#assignmentDate').value=new Date().toLocaleDateString('en-CA');$('#assignmentModalTitle').textContent=`Assign device to ${employee.name}`;$('#assignmentModalWrap').classList.remove('hidden');form.elements.asset_id.focus();
}
function closeAssignmentModal(){$('#assignmentModalWrap').classList.add('hidden')}
async function saveAssignment(event){event.preventDefault();const form=event.currentTarget,data={employee_id:Number(form.elements.employee_id.value),asset_id:Number(form.elements.asset_id.value)},button=$('#saveAssignment');button.disabled=true;try{const result=await api('/api/assignments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});closeAssignmentModal();await Promise.all([loadAssets(false),loadEmployees(false)]);updateBadges();render();showNotice(`Device assigned on ${date(result.assigned_date)}`,true)}catch(e){showNotice(e.message)}finally{button.disabled=false}}
async function returnDevice(assignmentId,device,person){if(!confirm(`Return ${device} from ${person}? The asset will move back to In stock.`))return;try{await api(`/api/assignments/${assignmentId}/return`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await Promise.all([loadAssets(false),loadEmployees(false)]);updateBadges();render();showNotice(`${device} returned to stock`,true)}catch(e){showNotice(e.message)}}
async function deleteEmployee(id){const e=state.employees.find(x=>x.id===id);if(!confirm(`Permanently delete ${e.name}? All devices must be returned first. A linked login account will also be deleted.`))return;try{const result=await api(`/api/employees/${id}`,{method:'DELETE'});await Promise.all([loadAssets(false),loadEmployees(false)]);updateBadges();render();showNotice(result.linked_login_deleted?'Employee and linked login deleted':'Employee deleted',true)}catch(error){showNotice(error.message)}}
async function resignEmployee(id){const e=state.employees.find(x=>x.id===id);if(!confirm(`Mark ${e.name} as resigned?\n\n${e.devices.length} assigned device${e.devices.length===1?'':'s'} will be returned to stock automatically, and kept in this employee's history.`))return;try{const r=await api(`/api/employees/${id}/resign`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await Promise.all([loadAssets(false),loadEmployees(false)]);updateBadges();render();showNotice(`${e.name} marked as resigned. ${r.assets_returned} device${r.assets_returned===1?'':'s'} returned to stock.`,true)}catch(error){showNotice(error.message)}}

function maintenance(){const urgent=state.assets.filter(a=>['Repair','Damaged','In warranty'].includes(a.status));return `<section class="attention"><div><h2>${urgent.length} assets need your attention</h2><p>Review damaged equipment, repair items and warranty cases.</p></div><span>Updated today</span></section><section class="maintenance-grid">${urgent.map(a=>`<article class="maintenance-card"><header>${identity(a)}${status(a.status)}</header><dl><div><dt>Assigned to</dt><dd>${esc(a.assigned_to)}</dd></div><div><dt>Location</dt><dd>${esc(a.location)}</dd></div><div><dt>Arrival date</dt><dd>${date(a.arrival_date)}</dd></div><div><dt>Distribution date</dt><dd>${date(a.distribution_date)}</dd></div><div><dt>Notes</dt><dd>${esc(a.notes||'No maintenance note')}</dd></div></dl>${state.me.can_write?`<button data-edit="${a.id}">◇ Update service status</button>`:''}</article>`).join('')}</section>${urgent.length?'':'<div class="empty panel"><b>Everything looks healthy</b><p>No assets are damaged, in warranty or under repair.</p></div>'}`}

function reports(){const cats=[...new Set(state.assets.map(a=>a.category))],dept=departments(),max=Math.max(...cats.map(c=>state.assets.filter(a=>a.category===c).length),1),inUse=state.assets.filter(a=>a.status==='In use').length,stock=state.assets.filter(a=>a.status==='In stock').length,attention=state.assets.filter(a=>['Damaged','In warranty','Repair'].includes(a.status)).length,quality=[['Serial number',a=>a.serial],['Assignment',a=>a.assigned_to&&a.assigned_to!=='Unassigned'],['Arrival date',a=>a.arrival_date],['Distribution date',a=>a.distribution_date],['Location',a=>a.location]];return `<section class="report-cards"><article><span>Assets in use</span><strong>${inUse}</strong><small>Currently distributed to employees</small></article><article><span>Available stock</span><strong>${stock}</strong><small>Ready for assignment</small></article><article><span>Need attention</span><strong>${attention}</strong><small>Damaged, warranty or repair items</small></article></section><section class="grid"><article class="panel"><header class="panel-head"><div><h2>Assets by category</h2><p>Current inventory mix</p></div><a class="secondary" href="/api/export">Download</a></header><div class="bars">${cats.map(c=>{const n=state.assets.filter(a=>a.category===c).length;return `<div class="bar"><span>${esc(c)}</span><div><i style="width:${n/max*100}%"></i></div><strong>${n}</strong></div>`}).join('')}</div></article><article class="panel"><header class="panel-head"><div><h2>Data completeness</h2><p>Record quality check</p></div><b>✓</b></header><div class="quality">${quality.map(([name,fn])=>{const p=state.assets.length?Math.round(state.assets.filter(fn).length/state.assets.length*100):0;return `<div class="quality-row"><div><span>${name}</span><b>${p}%</b></div><div><i style="width:${p}%"></i></div></div>`}).join('')}</div></article></section>`}

function networkView(){
  const q=state.search.toLowerCase();
  const rows=state.network.filter(d=>!q||[d.device_type,d.location,d.floor,d.brand,d.router_name,d.device_mac,d.ip_address].some(v=>(v||'').toLowerCase().includes(q)));
  const routers=state.network.filter(d=>d.device_type==='Router').length;
  const switches=state.network.filter(d=>d.device_type==='Switch').length;
  return `<section class="employee-summary"><article><span>Total network devices</span><strong>${state.network.length}</strong></article><article><span>Routers</span><strong>${routers}</strong></article><article><span>Switches</span><strong>${switches}</strong></article></section>
  <section class="panel"><header class="panel-head"><div><h2>Network devices</h2><p>Routers and switches across CCB, DM Plant, Dormitory, Workshop and UEB.</p></div>${state.me.can_write?'<button class="primary" data-add-network>＋ Add network device</button>':''}</header>
  <div class="table-scroll"><table><thead><tr><th>Device</th><th>Location</th><th>Brand</th><th>MAC address</th><th>IP address</th><th></th></tr></thead><tbody>${rows.map(d=>`<tr><td><div class="asset"><span class="asset-icon">${d.device_type==='Router'?'⇆':'⊞'}</span><div><strong>${esc(d.device_type)}</strong><small>${d.device_type==='Router'&&d.router_name?esc(d.router_name):'Network device'}</small></div></div></td><td><span class="department-badge">${esc(d.location)}</span>${d.floor?`<small class="cell-sub">${esc(d.floor)}</small>`:''}</td><td><b>${esc(d.brand)}</b></td><td>${d.device_mac?`<b>${esc(d.device_mac)}</b>`:'<span class="muted">—</span>'}</td><td>${d.device_type==='Router'?`<b>${esc(d.ip_address||'—')}</b>`:'<span class="muted">N/A</span>'}</td><td><div class="actions">${state.me.can_write?`<button title="Edit" data-network-edit="${d.id}">✎</button>`:''}${state.me.can_delete?`<button class="delete" title="Delete" data-network-delete="${d.id}">×</button>`:''}</div></td></tr>`).join('')}</tbody></table>${rows.length?'':'<div class="empty"><b>No network devices yet</b><p>Add a router or switch to begin tracking plant network hardware.</p></div>'}</div></section>`;
}

function updateNetworkBrandOptions(selected=''){
  const form=$('#networkForm'),type=form.elements.device_type.value,brands=brandsFor(type);
  form.elements.brand.innerHTML=(type?'<option value="">Select brand</option>':'<option value="">Select device first</option>')+brands.map(b=>`<option${b===selected?' selected':''}>${esc(b)}</option>`).join('');
}
function updateNetworkFloorOptions(selected=''){
  const form=$('#networkForm'),loc=form.elements.location.value,floors=floorsFor(loc),field=$('#networkFloorField');
  if(floors.length){
    form.elements.floor.innerHTML='<option value="">Select floor</option>'+floors.map(f=>`<option${f===selected?' selected':''}>${esc(f)}</option>`).join('');
    field.classList.remove('hidden');
  }else{
    form.elements.floor.innerHTML='<option value="">Select floor</option>';
    field.classList.add('hidden');
  }
}
function toggleNetworkIp(){const form=$('#networkForm'),isRouter=form.elements.device_type.value==='Router';$('#networkIpField').classList.toggle('hidden',!isRouter);if(!isRouter)form.elements.ip_address.value=''}
function toggleNetworkRouterName(){const form=$('#networkForm'),isRouter=form.elements.device_type.value==='Router';$('#networkRouterNameField').classList.toggle('hidden',!isRouter);if(!isRouter)form.elements.router_name.value=''}
function onNetworkDeviceTypeChange(){updateNetworkBrandOptions();toggleNetworkIp();toggleNetworkRouterName()}
function onNetworkLocationChange(){updateNetworkFloorOptions()}
function openNetworkModal(id){
  if(!state.me.can_write)return showNotice('Write permission is required');
  const form=$('#networkForm');form.reset();form.elements.id.value='';
  if(id){const d=state.network.find(x=>x.id===id);form.elements.id.value=d.id;form.elements.device_type.value=d.device_type;form.elements.location.value=d.location;updateNetworkFloorOptions(d.floor||'');updateNetworkBrandOptions(d.brand);form.elements.router_name.value=d.router_name||'';form.elements.device_mac.value=d.device_mac||'';form.elements.ip_address.value=d.ip_address||'';$('#networkModalTitle').textContent=`Edit ${d.device_type}`;$('#saveNetwork').textContent='✓ Save changes'}
  else{updateNetworkFloorOptions();updateNetworkBrandOptions();$('#networkModalTitle').textContent='Add network device';$('#saveNetwork').textContent='✓ Add device'}
  toggleNetworkIp();toggleNetworkRouterName();$('#networkModalWrap').classList.remove('hidden');form.elements.device_type.focus();
}
function closeNetworkModal(){$('#networkModalWrap').classList.add('hidden')}
async function saveNetworkDevice(event){event.preventDefault();const form=event.currentTarget,id=form.elements.id.value,data={device_type:form.elements.device_type.value,location:form.elements.location.value,floor:form.elements.floor.value,brand:form.elements.brand.value,router_name:form.elements.router_name.value,device_mac:form.elements.device_mac.value,ip_address:form.elements.ip_address.value},button=$('#saveNetwork');button.disabled=true;try{await api(id?`/api/network-devices/${id}`:'/api/network-devices',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});closeNetworkModal();await loadNetwork();showNotice(id?'Network device updated successfully':'Network device added successfully',true)}catch(e){showNotice(e.message)}finally{button.disabled=false}}
async function removeNetworkDevice(id){const d=state.network.find(x=>x.id===id);if(!confirm(`Delete this ${d.device_type} (${d.brand})? This action cannot be undone.`))return;try{await api(`/api/network-devices/${id}`,{method:'DELETE'});await loadNetwork();showNotice('Network device deleted',true)}catch(e){showNotice(e.message)}}

function settings(){
  const dark=$('#app').classList.contains('dark');
  const account=`<article class="panel setting"><span class="setting-icon">${esc(initials(state.me.full_name))}</span><div><h2>${esc(state.me.full_name)}</h2><p>@${esc(state.me.username)} • ${state.me.is_main_admin?'Main Administrator':state.me.role==='admin'?'Administrator':'User'}</p><button class="secondary" id="changePassword">Change password</button></div></article>`;
  const appearance=`<article class="panel setting"><span class="setting-icon">◐</span><div><h2>Appearance</h2><p>Choose the interface theme for this device.</p><div class="theme-options"><button data-theme="light" class="${dark?'':'selected'}">☀ Light</button><button data-theme="dark" class="${dark?'selected':''}">◐ Dark</button></div></div></article>`;
  const org=`<article class="panel setting"><img class="setting-logo" src="/assets/aps.png" alt="Aurora"><div><h2>Aurora organization</h2><p>Aurora Power Solutions Ltd. (demo company)</p><span class="permission-summary">${state.me.is_main_admin?'Main Admin • Full access':state.me.role==='user'?'My assigned assets only':[state.me.can_read&&'Read',state.me.can_write&&'Add/Edit',state.me.can_delete&&'Delete'].filter(Boolean).join(' • ')||'No inventory permission'}</span>${state.me.is_main_admin?'<button class="secondary manage-access" id="openAccessControl">Manage users &amp; permissions →</button>':''}</div></article>`;
  return `<section class="settings-grid">${account}${appearance}${org}</section>`;
}

function accessControl(){return state.me.is_main_admin?`<section class="access-intro"><div><span>MAIN ADMINISTRATOR ONLY</span><h2>Employee-based login accounts</h2><p>Select an Employee ID to auto-fill the name, designation and username. Users only see assets assigned to them; Administrators receive the permissions selected here.</p></div><button class="primary" data-add-user>＋ Add login account</button></section>${userManagement()}`:noAccess()}

function userManagement(){return `<section class="panel users-panel"><header class="panel-head"><div><h2>System login accounts</h2><p>Every new account is linked to one record from the Employee list.</p></div></header><div id="usersContent"><div class="loading">Loading users…</div></div></section>`}

async function loadUsers(){
  if(!state.me.is_main_admin)return;
  try{const data=await api('/api/users');state.users=data.users||[];renderUsers()}
  catch(e){showNotice(e.message)}
}

function renderUsers(){const box=$('#usersContent');if(!box)return;box.innerHTML=`<div class="table-scroll"><table><thead><tr><th>Name</th><th>Employee ID</th><th>Designation</th><th>Login</th><th>Role</th><th>Read</th><th>Write</th><th>Delete</th><th>Status</th><th></th></tr></thead><tbody>${state.users.map(u=>`<tr><td><div class="asset"><span class="avatar">${initials(u.full_name)}</span><div><strong>${esc(u.full_name)}</strong></div></div></td><td><strong>${esc(u.employee_id)}</strong></td><td>${esc(u.designation)}</td><td>@${esc(u.username)}</td><td><span class="role-badge">${u.is_main_admin?'Main Admin':u.role==='admin'?'Administrator':'User'}</span></td><td>${permissionIcon(u.can_read)}</td><td>${permissionIcon(u.can_write)}</td><td>${permissionIcon(u.can_delete)}</td><td>${u.active?'<span class="status active-status">Active</span>':'<span class="status retired-status">Disabled</span>'}</td><td><div class="actions">${u.is_main_admin?'<span class="muted">Protected</span>':`<button data-user-edit="${u.id}" title="Edit user">✎</button><button data-user-delete="${u.id}" class="delete" title="Delete user">×</button>`}</div></td></tr>`).join('')}</tbody></table></div>`;bindUserActions()}
function permissionIcon(value){return value?'<span class="permission yes">✓ Allowed</span>':'<span class="permission no">— Denied</span>'}

function bindView(){
  document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{state.view=b.dataset.go;render()});
  document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openModal(Number(b.dataset.edit)));
  document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>removeAsset(Number(b.dataset.delete)));
  document.querySelectorAll('[data-add-employee]').forEach(b=>b.onclick=()=>openEmployeeModal());
  document.querySelectorAll('[data-employee-edit]').forEach(b=>b.onclick=()=>openEmployeeModal(Number(b.dataset.employeeEdit)));
  document.querySelectorAll('[data-employee-delete]').forEach(b=>b.onclick=()=>deleteEmployee(Number(b.dataset.employeeDelete)));
  document.querySelectorAll('[data-resign]').forEach(b=>b.onclick=()=>resignEmployee(Number(b.dataset.resign)));
  document.querySelectorAll('[data-assign]').forEach(b=>b.onclick=()=>openAssignmentModal(Number(b.dataset.assign)));
  document.querySelectorAll('[data-return]').forEach(b=>b.onclick=()=>returnDevice(Number(b.dataset.return),b.dataset.device,b.dataset.person));
  document.querySelectorAll('[data-add-asset]').forEach(b=>b.onclick=()=>openModal());
  document.querySelectorAll('[data-import-asset]').forEach(b=>b.onclick=()=>openImportModal('asset'));
  document.querySelectorAll('[data-import-employee]').forEach(b=>b.onclick=()=>openImportModal('employee'));
  document.querySelectorAll('[data-add-network]').forEach(b=>b.onclick=()=>openNetworkModal());
  document.querySelectorAll('[data-network-edit]').forEach(b=>b.onclick=()=>openNetworkModal(Number(b.dataset.networkEdit)));
  document.querySelectorAll('[data-network-delete]').forEach(b=>b.onclick=()=>removeNetworkDevice(Number(b.dataset.networkDelete)));
  $('#statusFilter')?.addEventListener('change',e=>{state.status=e.target.value;render()});
  $('#categoryFilter')?.addEventListener('change',e=>{state.category=e.target.value;render()});
  $('#employeeSearch')?.addEventListener('input',e=>{
    const pos=e.target.selectionStart;
    state.employeeSearch=e.target.value;
    render();
    const el=$('#employeeSearch');
    if(el){el.focus();el.setSelectionRange(pos,pos)}
  });
  document.querySelectorAll('[data-theme]').forEach(b=>b.onclick=()=>setTheme(b.dataset.theme==='dark'));
  $('#changePassword')?.addEventListener('click',openPasswordModal);
  $('#openAccessControl')?.addEventListener('click',()=>{state.view='access';render()});
  document.querySelectorAll('[data-add-user]').forEach(button=>button.addEventListener('click',()=>openUserModal()));
  if(state.view==='access'&&state.me.is_main_admin)loadUsers();
}

function setTheme(dark){$('#app').classList.toggle('dark',dark);document.body.classList.toggle('dark-body',dark);localStorage.setItem('aps-theme',dark?'dark':'light');if(state.me)render()}

function openModal(id){
  if(!state.me.can_write)return showNotice('Write permission is required');
  const form=$('#assetForm');form.reset();form.elements.id.value='';
  const editing=!!id,a=editing?state.assets.find(x=>x.id===id):{};
  // dependent dropdowns (inject legacy values so existing records are preserved)
  fillSelect(form.elements.ram,RAM_OPTIONS,a.ram||'','Select RAM');
  fillSelect(form.elements.brand,ASSET_BRANDS,a.brand||'','Select brand');
  fillSelect(form.elements.location,ASSET_LOCATIONS,a.location||'','Select location');
  fillSelect(form.elements.ssd,STORAGE_OPTIONS,a.ssd||'','Select SSD');
  fillSelect(form.elements.hdd,STORAGE_OPTIONS,a.hdd||'','Select HDD');
  form.elements.processor_mfr.value=a.processor_mfr||'';
  updateProcessorFields(a.processor||'',a.cpu_generation||'');
  ['asset_tag','model','serial','ip_address','department','arrival_date','distribution_date','notes','cpu_series','category'].forEach(k=>{if(form.elements[k])form.elements[k].value=a[k]??''});
  // preserved-but-hidden fields (managed elsewhere)
  form.elements.name.value=a.name||'';form.elements.assigned_to.value=a.assigned_to||'';form.elements.cpu.value=a.cpu||'';
  // device status is only editable when editing an existing asset (e.g. maintenance)
  form.elements.status.value=a.status||'In stock';
  $('#statusField').classList.toggle('hidden',!editing);
  if(editing){$('#modalEyebrow').textContent='UPDATE INVENTORY RECORD';$('#modalTitle').textContent=`Edit ${a.asset_tag}`;$('#saveAsset').textContent='✓ Save changes'}
  else{$('#modalEyebrow').textContent='NEW INVENTORY RECORD';$('#modalTitle').textContent='Add IT asset';$('#saveAsset').textContent='✓ Add asset'}
  toggleComputerSpecs();toggleIpField();$('#modalWrap').classList.remove('hidden');form.elements.asset_tag.focus();
}
function updateProcessorFields(procSel='',genSel=''){
  const form=$('#assetForm'),mfr=form.elements.processor_mfr.value;
  fillSelect(form.elements.processor,processorsFor(mfr),procSel,mfr?'Select processor':'Select manufacturer first');
  fillSelect(form.elements.cpu_generation,generationsFor(mfr),genSel,mfr?'Select generation':'Select manufacturer first');
  toggleSeriesField();
}
function toggleSeriesField(){const form=$('#assetForm');$('#seriesField').classList.toggle('hidden',!form.elements.cpu_generation.value);if(!form.elements.cpu_generation.value)form.elements.cpu_series.value=''}
function onProcessorMfrChange(){updateProcessorFields()}
function toggleComputerSpecs(){const category=$('#assetForm').elements.category.value;$('#computerSpecs').classList.toggle('hidden',!['Laptop','Desktop'].includes(category))}
function toggleIpField(){const form=$('#assetForm'),hide=IP_LESS_CATEGORIES.includes(form.elements.category.value);$('#assetIpField').classList.toggle('hidden',hide);if(hide)form.elements.ip_address.value=''}
function onAssetCategoryChange(){toggleComputerSpecs();toggleIpField()}
function closeModal(){$('#modalWrap').classList.add('hidden')}
async function saveAsset(event){event.preventDefault();const form=event.currentTarget,data=Object.fromEntries(new FormData(form)),id=data.id;delete data.id;const button=$('#saveAsset'),old=button.textContent;button.disabled=true;button.textContent='Saving…';try{await api(id?`/api/assets/${id}`:'/api/assets',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});closeModal();await loadAssets();showNotice(id?'Asset updated successfully':'Asset added successfully',true)}catch(e){showNotice(e.message)}finally{button.disabled=false;button.textContent=old}}
async function removeAsset(id){const a=state.assets.find(x=>x.id===id);if(!confirm(`Delete ${a.asset_tag}? This action cannot be undone.`))return;try{await api(`/api/assets/${id}`,{method:'DELETE'});await loadAssets();showNotice('Asset deleted',true)}catch(e){showNotice(e.message)}}

const IMPORT_CONFIG={
  asset:{title:'Import assets from Excel',endpoint:'/api/assets/import',template:'/templates/aps-assets-template.xlsx',
    intro:'Upload a .xlsx or .csv file. Row 1 must be the header. Required columns: asset_tag and category. Dates use YYYY-MM-DD. IP is ignored for Monitor, Mouse, Keyboard and Printer.',reload:loadAssets},
  employee:{title:'Import employees from Excel',endpoint:'/api/employees/import',template:'/templates/aps-employees-template.xlsx',
    intro:'Upload a .xlsx or .csv file. Row 1 must be the header. Required columns: name, employee_id (ID), designation and department. Department must be one of I&C, EMD, MMD, A&P, EHS, OPD, RPQC.',reload:loadEmployees}
};
function openImportModal(type){
  if(!state.me.can_write)return showNotice('Write permission is required');
  const cfg=IMPORT_CONFIG[type];state.importType=type;
  $('#importModalTitle').textContent=cfg.title;
  $('#importIntro').textContent=cfg.intro;
  $('#importTemplateLink').setAttribute('href',cfg.template);
  $('#importFile').value='';
  const box=$('#importResult');box.classList.add('hidden');box.innerHTML='';
  $('#importModalWrap').classList.remove('hidden');
}
function closeImportModal(){$('#importModalWrap').classList.add('hidden')}
function readFileAsBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]||'');reader.onerror=()=>reject(new Error('Could not read the file'));reader.readAsDataURL(file)})}
async function runImport(){
  const cfg=IMPORT_CONFIG[state.importType],input=$('#importFile'),file=input.files&&input.files[0];
  if(!file)return showNotice('Choose an Excel or CSV file first');
  const button=$('#runImport'),old=button.textContent;button.disabled=true;button.textContent='Importing…';
  try{
    const data=await readFileAsBase64(file);
    const result=await api(cfg.endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,data})});
    const box=$('#importResult');box.classList.remove('hidden');
    const errorList=(result.errors||[]).length?`<details class="import-errors" open><summary>${result.errors.length} row${result.errors.length===1?'':'s'} skipped</summary><ul>${result.errors.map(e=>`<li>Row ${esc(e.row)}: ${esc(e.reason)}</li>`).join('')}</ul></details>`:'';
    box.innerHTML=`<div class="import-summary ${result.added?'ok':'warn'}"><strong>${result.added} record${result.added===1?'':'s'} added</strong>${result.skipped?` • ${result.skipped} skipped`:''}</div>${errorList}`;
    await cfg.reload(false);updateBadges();render();
    showNotice(result.added?`${result.added} record${result.added===1?'':'s'} imported successfully`:'No new records were imported',!!result.added);
    input.value='';
  }catch(e){showNotice(e.message)}
  finally{button.disabled=false;button.textContent=old}
}

function openUserModal(id){
  const form=$('#userForm');form.reset();form.elements.id.value='';form.elements.active.checked=true;form.elements.can_read.checked=true;form.elements.password.required=true;
  const current=id?state.users.find(x=>x.id===id):null,used=new Set(state.users.filter(u=>u.employee_pk&&u.id!==id).map(u=>Number(u.employee_pk)));
  const choices=state.employees.filter(e=>e.active&&!used.has(Number(e.id)));
  form.elements.employee_pk.innerHTML='<option value="">Select from employee list</option>'+choices.map(e=>`<option value="${e.id}">${esc(e.employee_id)} — ${esc(e.name)}</option>`).join('');
  if(current){form.elements.id.value=current.id;form.elements.employee_pk.value=current.employee_pk||'';form.elements.role.value=current.role;form.elements.can_read.checked=current.can_read;form.elements.can_write.checked=current.can_write;form.elements.can_delete.checked=current.can_delete;form.elements.active.checked=current.active;form.elements.password.required=false;form.elements.password.placeholder='Leave blank to keep current password';$('#userModalTitle').textContent=`Edit ${current.full_name}`}
  else{$('#userModalTitle').textContent='Add user from employee list';form.elements.password.placeholder='Minimum 8 characters'}
  fillUserFromEmployee();toggleRolePermissions();$('#userModalWrap').classList.remove('hidden');form.elements.employee_pk.focus();
}
function closeUserModal(){$('#userModalWrap').classList.add('hidden')}
function usernameFromEmployee(employee,editingId=''){if(!employee)return'';const parts=employee.name.trim().split(/\s+/),first=(parts[0]||'user').toLowerCase().replace(/[^a-z0-9]/g,''),base=['md','mohammad'].includes(first)&&parts[1]?parts[1].toLowerCase().replace(/[^a-z0-9]/g,''):first||'user',used=name=>state.users.some(u=>u.id!==Number(editingId)&&u.username.toLowerCase()===name.toLowerCase());let candidate=base;if(!used(candidate))return candidate;const suffix=employee.employee_id.toLowerCase().replace(/[^a-z0-9]/g,'').slice(-4)||'1';candidate=base+suffix;let n=2;while(used(candidate))candidate=base+n++;return candidate}
function fillUserFromEmployee(){const form=$('#userForm'),employee=state.employees.find(e=>e.id===Number(form.elements.employee_pk.value));form.elements.full_name.value=employee?.name||'';form.elements.designation.value=employee?.designation||'';form.elements.username.value=usernameFromEmployee(employee,form.elements.id.value)}
function toggleRolePermissions(){const form=$('#userForm'),admin=form.elements.role.value==='admin';form.elements.can_read.checked=true;['can_read','can_write','can_delete'].forEach(name=>{const el=form.elements[name];el.disabled=!admin;if(!admin&&name!=='can_read')el.checked=false});$('#roleHelp').textContent=admin?'Select the inventory permissions granted by the Main Admin.':'Users can only see assets currently assigned to their Employee ID.'}
async function saveUser(event){event.preventDefault();const form=event.currentTarget,id=form.elements.id.value,data={employee_pk:Number(form.elements.employee_pk.value),role:form.elements.role.value,password:form.elements.password.value,can_read:form.elements.can_read.checked,can_write:form.elements.can_write.checked,can_delete:form.elements.can_delete.checked,active:form.elements.active.checked};const button=$('#saveUser');button.disabled=true;try{const result=await api(id?`/api/users/${id}`:'/api/users',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});closeUserModal();await loadUsers();showNotice(id?'Account updated successfully':`Account created. Username: ${result.username}`,true)}catch(e){showNotice(e.message)}finally{button.disabled=false}}
async function removeUser(id){const u=state.users.find(x=>x.id===id);if(!confirm(`Delete user ${u.full_name}?`))return;try{await api(`/api/users/${id}`,{method:'DELETE'});await loadUsers();showNotice('User deleted',true)}catch(e){showNotice(e.message)}}
function bindUserActions(){document.querySelectorAll('[data-user-edit]').forEach(b=>b.onclick=()=>openUserModal(Number(b.dataset.userEdit)));document.querySelectorAll('[data-user-delete]').forEach(b=>b.onclick=()=>removeUser(Number(b.dataset.userDelete)))}

function openPasswordModal(){$('#passwordForm').reset();$('#passwordModalWrap').classList.remove('hidden');$('#passwordForm').elements.current_password.focus()}
function closePasswordModal(){if(!state.me?.must_change_password)$('#passwordModalWrap').classList.add('hidden')}
async function changePassword(event){event.preventDefault();const form=event.currentTarget;if(form.elements.new_password.value!==form.elements.confirm_password.value)return showNotice('New passwords do not match');try{await api('/api/auth/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:form.elements.current_password.value,new_password:form.elements.new_password.value})});state.me.must_change_password=false;$('#passwordModalWrap').classList.add('hidden');form.reset();showNotice('Password changed successfully',true)}catch(e){showNotice(e.message)}}

function openForcePasswordModal(){const form=$('#forcePasswordForm');form.reset();$('#forcePasswordModalWrap').classList.remove('hidden');form.elements.new_password.focus()}
async function submitForcePassword(event){event.preventDefault();const form=event.currentTarget,np=form.elements.new_password.value,cp=form.elements.confirm_password.value;if(np!==cp)return showNotice('New passwords do not match');if(np.length<8)return showNotice('New password must be at least 8 characters');const button=$('#saveForcePassword');button.disabled=true;try{await api('/api/auth/set-initial-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_password:np})});state.me.must_change_password=false;$('#forcePasswordModalWrap').classList.add('hidden');form.reset();showNotice('Password changed successfully. Welcome!',true)}catch(e){showNotice(e.message)}finally{button.disabled=false}}

function bindGlobal(){
  $('#loginForm').onsubmit=login;$('#logout').onclick=logout;
  document.querySelectorAll('.show-password').forEach(b=>b.onclick=()=>{const input=b.parentElement.querySelector('input');input.type=input.type==='password'?'text':'password'});
  $('#nav').onclick=e=>{const b=e.target.closest('[data-view]');if(!b)return;state.view=b.dataset.view;$('#sidebar').classList.remove('open');render()};
  $('#search').oninput=e=>{state.search=e.target.value;if(state.me?.can_read&&!['assets','employees'].includes(state.view))state.view='assets';render()};
  $('#closeModal').onclick=closeModal;$('#cancelModal').onclick=closeModal;$('#modalWrap').onmousedown=e=>{if(e.target===e.currentTarget)closeModal()};$('#assetForm').onsubmit=saveAsset;$('#assetCategory').onchange=onAssetCategoryChange;$('#assetForm').elements.processor_mfr.onchange=onProcessorMfrChange;$('#assetForm').elements.cpu_generation.onchange=toggleSeriesField;
  $('#closeEmployeeModal').onclick=closeEmployeeModal;$('#cancelEmployeeModal').onclick=closeEmployeeModal;$('#employeeModalWrap').onmousedown=e=>{if(e.target===e.currentTarget)closeEmployeeModal()};$('#employeeForm').onsubmit=saveEmployee;$('#employeeDepartment').onchange=()=>populateDesignationOptions();
  $('#closeAssignmentModal').onclick=closeAssignmentModal;$('#cancelAssignmentModal').onclick=closeAssignmentModal;$('#assignmentModalWrap').onmousedown=e=>{if(e.target===e.currentTarget)closeAssignmentModal()};$('#assignmentForm').onsubmit=saveAssignment;
  $('#closeUserModal').onclick=closeUserModal;$('#cancelUserModal').onclick=closeUserModal;$('#userModalWrap').onmousedown=e=>{if(e.target===e.currentTarget)closeUserModal()};$('#userForm').onsubmit=saveUser;$('#userForm').elements.role.onchange=toggleRolePermissions;$('#userForm').elements.employee_pk.onchange=fillUserFromEmployee;
  $('#closeNetworkModal').onclick=closeNetworkModal;$('#cancelNetworkModal').onclick=closeNetworkModal;$('#networkModalWrap').onmousedown=e=>{if(e.target===e.currentTarget)closeNetworkModal()};$('#networkForm').onsubmit=saveNetworkDevice;$('#networkForm').elements.device_type.onchange=onNetworkDeviceTypeChange;$('#networkForm').elements.location.onchange=onNetworkLocationChange;
  $('#closePasswordModal').onclick=closePasswordModal;$('#cancelPasswordModal').onclick=closePasswordModal;$('#passwordForm').onsubmit=changePassword;
  $('#closeImportModal').onclick=closeImportModal;$('#cancelImportModal').onclick=closeImportModal;$('#importModalWrap').onmousedown=e=>{if(e.target===e.currentTarget)closeImportModal()};$('#runImport').onclick=runImport;
  $('#forcePasswordForm').onsubmit=submitForcePassword;
  $('#topbarProfile')?.addEventListener('click',()=>{if(state.me?.must_change_password)return;state.view='settings';$('#sidebar').classList.remove('open');render()});
  $('#theme').onclick=()=>setTheme(!$('#app').classList.contains('dark'));$('#openNav').onclick=()=>$('#sidebar').classList.add('open');$('#closeNav').onclick=()=>$('#sidebar').classList.remove('open');
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'&&state.me?.can_read){e.preventDefault();$('#search').focus()}if(e.key==='Escape'){closeModal();closeEmployeeModal();closeAssignmentModal();closeUserModal();closeNetworkModal();closePasswordModal();closeImportModal()}});
  const dark=localStorage.getItem('aps-theme')==='dark';$('#app').classList.toggle('dark',dark);document.body.classList.toggle('dark-body',dark);
}

start();
